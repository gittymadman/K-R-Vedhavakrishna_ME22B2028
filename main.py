import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from typing import List

import asyncpg
import websockets

CONFIG = {
    "symbols": ["btcusdt", "ethusdt"],        # lowercase symbol names (no @trade suffix)
    "batch_size": 100,                        # how many ticks to insert at once
    "flush_interval_s": 2.0,                  # flush queue at least every N seconds
    "postgres": {
        "host": "localhost",
        "port": 5433,
        "user": "postgres",
        "password": "password",
        "database": "market_data"
    }
}
# -----------------------------

# build combined stream URL for trade streams
def combined_stream_url(symbols: List[str]) -> str:
    stream_names = "/".join(f"{s.lower()}@trade" for s in symbols)
    return f"wss://stream.binance.com:9443/stream?streams={stream_names}"

# parse Binance trade message (from combined stream wrapper)
def parse_trade_message(msg: dict):
    """
    Binance combined stream message format:
    {
      "stream": "btcusdt@trade",
      "data": {
        "e": "trade",     // event type
        "E": 123456789,   // event time
        "s": "BTCUSDT",   // symbol
        "t": 12345,       // trade id
        "p": "0.001",     // price
        "q": "100",       // quantity
        "b": 88,          // buyer order id
        "a": 50,          // seller order id
        "T": 123456785,   // trade time
        "m": true,        // is the buyer the market maker?
        "M": true         // ignore
      }
    }
    """
    data = msg.get("data", msg)  # sometimes you may be connected to single-stream (not combined)
    # prefer trade time T, fallback to event time E
    trade_time_ms = data.get("T") or data.get("E")
    ts = datetime.fromtimestamp(trade_time_ms / 1000.0, tz=timezone.utc)
    symbol = data.get("s")
    price = float(data.get("p"))
    qty = float(data.get("q"))
    return {"ts": ts, "symbol": symbol, "price": price, "qty": qty}

# Postgres helper
class PostgresWriter:
    def __init__(self, pg_conf, batch_size=100):
        self.pg_conf = pg_conf
        self.pool = None
        self.batch_size = batch_size

    async def start(self):
        self.pool = await asyncpg.create_pool(
            host=self.pg_conf["host"],
            port=self.pg_conf.get("port", 5432),
            user=self.pg_conf["user"],
            password=self.pg_conf["password"],
            database=self.pg_conf["database"],
            min_size=1,
            max_size=5,
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def insert_batch(self, rows):
        """
        rows: list of dicts: {'ts': datetime, 'symbol': str, 'price': float, 'qty': float}
        """
        if not rows:
            return
        insert_sql = """
        INSERT INTO ticks (ts, symbol, price, qty)
        VALUES ($1, $2, $3, $4)
        """
        async with self.pool.acquire() as conn:
            # use a transaction for batch
            async with conn.transaction():
                await conn.executemany(insert_sql, [(r["ts"], r["symbol"], r["price"], r["qty"]) for r in rows])

# Main ingestion class
class BinanceIngest:
    def __init__(self, symbols, pg_conf, batch_size=100, flush_interval_s=2.0):
        self.url = combined_stream_url(symbols)
        self.queue = []
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.pg = PostgresWriter(pg_conf, batch_size=batch_size)
        self._ws = None
        self._stop = asyncio.Event()

    async def start(self):
        await self.pg.start()
        # spawn flusher
        flusher_task = asyncio.create_task(self._flusher_loop())
        # start websocket loop (runs until stop)
        try:
            await self._ws_loop()
        finally:
            # ensure flusher stops
            self._stop.set()
            await flusher_task
            await self.pg.close()

    async def _ws_loop(self):
        reconnect_delay = 1
        while not self._stop.is_set():
            try:
                print(f"[INFO] Connecting to Binance: {self.url}")
                async with websockets.connect(self.url, max_size=2**25) as ws:
                    self._ws = ws
                    print("[INFO] Connected.")
                    reconnect_delay = 1
                    async for raw in ws:
                        # parse raw json
                        try:
                            msg = json.loads(raw)
                        except Exception as e:
                            print("[WARN] Failed JSON parse:", e)
                            continue
                        # messages from combined stream have 'stream' + 'data'
                        try:
                            tick = parse_trade_message(msg)
                        except Exception as e:
                            print("[WARN] Failed to parse trade message:", e, "raw:", raw[:200])
                            continue

                        # show to stdout
                        # convert UTC timestamp to ISO string
                        # print(f"{tick['ts'].isoformat()} {tick['symbol']} price={tick['price']} qty={tick['qty']}")

                        # queue for DB insert
                        self.queue.append(tick)
                        if len(self.queue) >= self.batch_size:
                            await self._flush_queue()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[ERROR] Connection error: {exc!r}. Reconnecting in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30)
            finally:
                self._ws = None

    async def stop(self):
        self._stop.set()
        if self._ws:
            await self._ws.close()

    async def _flush_queue(self):
        if not self.queue:
            return
        to_insert = self.queue
        self.queue = []
        try:
            await self.pg.insert_batch(to_insert)
            print(f"[DB] Inserted {len(to_insert)} rows")
        except Exception as e:
            # on DB failure, push rows back to queue (front)
            print("[ERROR] DB insert failed:", e)
            # prepend the failed rows back to queue
            self.queue = to_insert + self.queue
            # small sleep to avoid busy loop
            await asyncio.sleep(1)

    async def _flusher_loop(self):
        while not self._stop.is_set():
            await asyncio.sleep(self.flush_interval_s)
            if self.queue:
                await self._flush_queue()

# Graceful shutdown for signals
def setup_signal_handlers(loop, ingest: BinanceIngest):
    def _signal_handler():
        print("[INFO] Received stop signal. Shutting down...")
        asyncio.create_task(ingest.stop())
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows fallback
            pass

async def main():
    symbols = CONFIG["symbols"]
    batch_size = CONFIG["batch_size"]
    flush_interval_s = CONFIG["flush_interval_s"]
    pg_conf = CONFIG["postgres"]

    ingest = BinanceIngest(symbols, pg_conf, batch_size=batch_size, flush_interval_s=flush_interval_s)
    loop = asyncio.get_running_loop()
    setup_signal_handlers(loop, ingest)
    try:
        await ingest.start()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print("[FATAL] Exception in main:", e)
    finally:
        print("[INFO] Exiting.")

if __name__ == "__main__":
    # Run the async main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt - exiting.")
        sys.exit(0)
