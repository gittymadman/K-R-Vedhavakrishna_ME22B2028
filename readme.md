# 💹 Real-Time Crypto Trading Dashboard

Hey! 👋  
This is my project for building a real-time crypto analytics and trading signals dashboard. It pulls **live tick data** from Binance (Bitcoin and Ethereum as of now), runs some cool analytics like **spread**, **z-score**, and even finds potential **entry/exit points** based on pair trading strategies.  

There are also metrics like **support/resistance levels**, **cross-asset correlations**, and more. All of this is displayed nicely in a **Dash** app with interactive charts.

---

## 🔧 What This Project Can Do

- 📈 Displays **live charts** for BTC and ETH prices  
- ⚖️ Calculates spread between two cryptos  
- 🧠 Computes z-scores and visualizes **entry/exit markers**  
- 🔍 Shows **cross-correlation heatmaps** (e.g. BTC vs ETH vs BNB, etc.)  
- 🛠️ Generates stats at different time intervals (like every 1 minute, 5 minutes, etc.)  
- 🔔 Gives **rule-based alerts**  
- 📄 Lets you **download tables** as CSVs to analyze later  

---

## 🏗️ How It Works (Architecture)

```plaintext
Binance WebSocket --> Python Script --> PostgreSQL DB --> Analytics Engine --> Dash Dashboard
