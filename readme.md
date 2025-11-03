# Real-Time Crypto Trading Dashboard

Hey! 👋  
This is my project for building a real-time crypto analytics and trading signals dashboard. It pulls **live tick data** from Binance (Bitcoin and Ethereum as of now), runs some cool analytics like **spread**, **z-score**, and even finds potential **entry/exit points** based on pair trading strategies.  

There are also metrics like **support/resistance levels**, **cross-asset correlations**, and more. All of this is displayed nicely in a **Dash** app with interactive charts.

---

### What This Project Can Do ###

- Displays **live charts** for BTC and ETH prices  
- Calculates spread between two cryptos  
- Computes z-scores and visualizes **entry/exit markers**  
- Shows **cross-correlation heatmaps** (e.g. BTC vs ETH vs BNB, etc.)  
- Generates stats at different time intervals (like every 1 minute, 5 minutes, etc.)  
- Gives **rule-based alerts**  
- Lets you **download tables** as CSVs to analyze later  

---

## How It Works (Architecture)

```plaintext
Binance WebSocket --> Python Script --> PostgreSQL DB --> Analytics Engine --> Dash Dashboard
```
# Explanation of Different Files 
1. **Main.py** -
   a. This acts as the backend of the project. It reads binance data from the Binance API for the symbols. This data is then downsampled into 4 rows -> ts (timestamp), symbol, price, qty.
   b. We take a batch size of 100 or a time frame of 2 seconds to get data from the API, this is then pushed into the postgres db smoothly using pythton's asyncpg library.
   c.Then comes - **BinanceIngest**, I hadn't tried putting realtime data into postgres and face difficulties in this, so used chatgpt to write this part of the code and the helper functions associated with it.

2. **Analytics.py** - This file contains all the analytics functions required or which I tried out.
   a. Stats - Returs the returs the latest price of the crypto read, mean,standard deviation,min,max which will be used in other functions
   b. OLS Regression - Used to find the Hedge Ratio i.e How is one crypto related to other. This helps traders to mitigate losses, if OLS is negative for BTC and ETH -> traders will buy them so that if BTC goes down, then ETH will go up.
   c. I have the code for Robust Regression methods and Kalman filter - but haven't used them as I didn't know about them full (saw some youtube videos though)
   d. THen we have the Spread and z_score calculation which will be used to find the entry and exit points in a trade.
   e. ADF Test is used to check whether a time series is stationary or not, if it is stationary, the future price can be predicted easier.
   f. backtest_mean_reversion - is used to find the positions of entry and exit based on z_score
   g. **full_pair_analytics** - All the above functions are called in this final function to combine them as a single package which will be imported in **app.py** whose values will be displaed in the frontend.

3. **App.py** - I've used Python Dash for the frontend, as I have used it in my previous internship. This module has the candle Stick graph to visualize the volume and price of crypto-currency. All the metrics from Analytics.py and a graph showing the z-score and entry and exit points with it. There is also a alert message for showing when to enter and when to exit.

4. **Run_all.py** - As the project is to run using a single command at cmd, I created another file to run both these files as a subprocess, first **Main.py** will run and after 30 seconds **Analytics.py** will run. This is just to collect some crypto data from the Binance API which will be stored in postgres data, from where **Analytics.py** will read the data for plots and analytics.



 # AI Usage
I used AI (ChatGPT and Gemini) to understand and build parts of my real-time crypto data ingestion system. It helped me break down concepts like async WebSocket connections, parsing trade messages from Binance, and saving data in Postgres. Instead of spending hours Googling everything, I was able to ask specific questions and get clean, quick answers.

Some Prompts I Used:
"Can you explain this code in simple terms?"<br>
"How do I parse Binance WebSocket data?"\n
"How to use asyncpg with connection pooling?"\n
"How to stop an asyncio task cleanly?"\n
"Can you give me code to upload Binance Crypto data into postgres and explain what you are doing"
"Give SQL code to implement Candle diagrams for Crypto data"

Overall, AI made the whole process faster



