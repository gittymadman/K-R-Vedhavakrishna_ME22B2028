import pandas as pd
import plotly.graph_objs as go
from dash import Dash, dcc, html,dash_table
from dash.dependencies import Input, Output
from sqlalchemy import create_engine
from analytics import full_pair_analytics  # Import our analytics function
import plotly.express as px

# Database connection
DB_URL = 'postgresql://postgres:password@localhost:5433/market_data'
engine = create_engine(DB_URL)

# Dash App Setup
app = Dash(__name__)
app.layout = html.Div([
    html.H1("Live Crypto Candlestick & Pair Analytics - Binance API"),

    # Dropdown for symbol
    dcc.Dropdown(
        id="symbol-dropdown",
        options=[
            {"label": "BTC/USDT", "value": "BTCUSDT"},
            {"label": "ETH/USDT", "value": "ETHUSDT"},
        ],
        value="BTCUSDT",
        style={'width': '50%'}
    ),

    # Candlestick Graph
    dcc.Graph(id="candlestick-graph"),

    # Analytics Panel
    html.Div(id="analytics-panel", style={
        "margin-top": "20px", "background": "#ffffff", "padding": "15px", "border-radius": "8px",'border-color':'#000000'
    }),
    dcc.Graph(id='zscore-chart',figure={}),
    # Data update interval

    html.Br(),
    html.H4("Liquidity Filter (Minimum Volume)"),
    dcc.Slider(
        id='liq-filter',
        min=0,
        max=5,
        step=0.1,
        value=1,
        marks={i: f"{i}" for i in range(6)}
    ),

    #Alerts Section
    html.Div(id='rule-alerts'),

    #Correlation Heatmap
    html.Hr(),
    html.H4("Cross-Correlation Heatmap"),
    dcc.Graph(id='corr-heatmap', figure={}),

    #Stats Table with CSV Export
    html.Hr(),
    html.H4("Time-Series Stats Table (Last 100 PTs)"),
    dash_table.DataTable(
        id='stats-table',
        export_format="csv",
        page_size=10,
        style_table={'overflowX': 'auto'},
    ),


    dcc.Interval(
        id="interval-update",
        interval=5000,  # 5s updates
        n_intervals=0
    )])

def plot_zscore_with_signals(z, positions):
    fig = go.Figure()

    # Plot z-score
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(z.index, utc=True).tz_convert('Asia/Kolkata'),
        y=z,
        mode='lines',
        name='Z-Score'))

    # Add entry/exit thresholds
    fig.add_hline(y=2, line_dash='dash', line_color='red', annotation_text='Entry Threshold')
    fig.add_hline(y=0, line_dash='dash', line_color='green', annotation_text='Exit Threshold')

    # Mark entry and exit points
    entries = positions[positions == 1]
    exits = positions[positions == 0]

    fig.add_trace(go.Scatter(
        x=pd.to_datetime(entries.index, utc=True).tz_convert('Asia/Kolkata'),
        y=z.loc[entries.index],
        mode='markers',
        marker=dict(color='red', size=8, symbol='triangle-up'),
        name='Entry'))

    fig.add_trace(go.Scatter(
        x=pd.to_datetime(exits.index, utc=True).tz_convert('Asia/Kolkata'),
        y=z.loc[exits.index],
        mode='markers',
        marker=dict(color='green', size=8, symbol='triangle-down'),
        name='Exit'))

    fig.update_layout(
        title='Z-Score with Entry and Exit Points',
        xaxis_title='Time',
        yaxis_title='Z-Score',
        hovermode='x unified')

    return fig

@app.callback(
    [Output("candlestick-graph", "figure"),
     Output("analytics-panel", "children"),
     Output('zscore-chart', 'figure'),
     Output('corr-heatmap', 'figure'),
    Output('rule-alerts', 'children'),
    Output('stats-table', 'data'),
    Output('stats-table', 'columns')],

    [Input("interval-update", "n_intervals"),
     Input("symbol-dropdown", "value"),
     Input("liq-filter", "value")]
)
def update_dashboard(n_intervals, symbol,liq_filter):
    # Candlestick Data Query
    query = """
        WITH candlestick AS (
            SELECT
                date_trunc('minute', ts) AS bucket,
                price,
                qty,
                ts,
                ROW_NUMBER() OVER (
                    PARTITION BY date_trunc('minute', ts) 
                    ORDER BY ts ASC
                ) AS rn_asc,
                ROW_NUMBER() OVER (
                    PARTITION BY date_trunc('minute', ts) 
                    ORDER BY ts DESC
                ) AS rn_desc
            FROM ticks
            WHERE symbol = %s
            AND ts > NOW() - INTERVAL '3 hours'
        )
        SELECT
            bucket,
            MAX(CASE WHEN rn_asc = 1 THEN price END) AS open,
            MAX(price) AS high,
            MIN(price) AS low,
            MAX(CASE WHEN rn_desc = 1 THEN price END) AS close,
            SUM(qty) AS volume
        FROM candlestick
        GROUP BY bucket
        ORDER BY bucket;
    """

    df = pd.read_sql(query, engine, params=(symbol,))
    df['bucket'] = pd.to_datetime(df['bucket'], utc=True).dt.tz_convert('Asia/Kolkata')

    # Candlestick Graph
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df['bucket'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name="Candles"
            ),
            go.Bar(
                x=df['bucket'],
                y=df['volume'],
                name="Volume",
                marker=dict(opacity=0.2),
                yaxis='y2'
            )
        ]
    )
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        yaxis=dict(title='Price'),
        yaxis2=dict(title='Volume', overlaying='y', side='right'),
        template="plotly_dark",
        title=f"{symbol} Live Price (1m Candles)"
    )

    # Live Analytics
    btc_usdt = "BTCUSDT"
    eth_usdt = "ETHUSDT"

    # Compare current selected symbol with the other one for pair analysis
    analytics = full_pair_analytics(symbol, eth_usdt if symbol == btc_usdt else btc_usdt,engine)

    analytics_panel = [
    html.H3("Live Analytics"),
    html.P(f"Last Price X: {analytics['x_stats']['last_price']:.2f}"),
    html.P(f"Last Price Y: {analytics['y_stats']['last_price']:.2f}"),
    html.Hr(),
    html.P(f"Z-score: {analytics['latest_zscore']:.2f}"),
    html.P(f"Hedge Ratio (β): {analytics['beta']:.4f}"),
    html.P(f"Current Spread: {analytics['latest_spread']:.4f}"),
    html.Hr(),
    html.P(f"ADF Statistic: {analytics['adf']['adf_stat']:.4f}"),
    html.P(
        f"ADF p-value: {analytics['adf']['pvalue']:.4f} "
        f"{'(Stationary)' if analytics['adf']['pvalue'] < 0.05 else '(Non-Stationary)'}"
    ),
    html.Hr(),
    html.P(
        f"Rolling Correlation ({len(analytics['rolling_corr'])} pts): "
        f"{analytics['rolling_corr'].iloc[-1]:.4f}"
    ),
]

    zscore_fig = plot_zscore_with_signals(analytics['zscore'], analytics['positions'])

     # Fetch recent records for correlation and stats
    full_data_query = """
        SELECT ts, symbol, price, qty 
        FROM ticks
        WHERE ts > NOW() - INTERVAL '3 hours'
        ORDER BY ts
    """
    full_data = pd.read_sql(full_data_query, engine)
    full_data['ts'] = pd.to_datetime(full_data['ts'], utc=True).dt.tz_convert('Asia/Kolkata')

    # Apply Liquidity Filter
    filtered_data = full_data[full_data['qty'] >= liq_filter]

    # --- Cross-Correlation Heatmap ---
    corr_df = filtered_data.pivot_table(index='ts', columns='symbol', values='price')
    corr_matrix = corr_df.corr()
    corr_fig = px.imshow(corr_matrix, text_auto=True, title='Asset Price Correlation')

    # --- Rule-based Alerts ---
    alerts = []
    latest_row = analytics['zscore'].iloc[-1]
    if latest_row > 2:
        alerts.append(html.Div("🚨 Z-Score High Alert: Consider opening a short pair position", style={'color': 'red'}))
    elif latest_row < 0:
        alerts.append(html.Div("✅ Z-Score Below Threshold: Potential exit point", style={'color': 'green'}))
    else:
        alerts.append(html.Div("➖ No actionable z-score signal detected", style={'color': 'gray'}))

    # --- Stats Table with CSV Export ---
    stats_df = filtered_data[['ts', 'symbol', 'price', 'qty']].tail(100)
    stats_table = stats_df.to_dict('records')
    stats_columns = [{"name": i, "id": i} for i in stats_df.columns]

    return fig, analytics_panel, zscore_fig, corr_fig, alerts, stats_table, stats_columns

if __name__ == "__main__":
    app.run(debug=True)
