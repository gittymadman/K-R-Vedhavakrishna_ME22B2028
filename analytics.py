import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from sklearn.linear_model import HuberRegressor, TheilSenRegressor
from pykalman import KalmanFilter
import statsmodels.api as sm


def stats(df):
    return {
        'last_price': df['price'].iloc[-1],
        'mean': df['price'].mean(),
        'std': df['price'].std(),
        'min': df['price'].min(),
        'max': df['price'].max()
        # 'volume': df['qty'].sum()
    }


def ols_ratio(x, y): # tells how x moves w.r.t y or vice versa
    x = sm.add_constant(x)
    model = sm.OLS(y, x, missing='drop').fit()
    beta = model.params[1]
    intercept = model.params[0]
    return beta, intercept, model


def hedge_ratio_huber(x, y):
    reg = HuberRegressor().fit(x.values.reshape(-1, 1), y.values)
    return reg.coef_[0], reg.intercept_

def hedge_ratio_theilsen(x, y):
    reg = TheilSenRegressor().fit(x.values.reshape(-1, 1), y.values)
    return reg.coef_[0], reg.intercept_


def kalman_hedge_ratio(x, y):
    observations = y.values - x.values
    kf = KalmanFilter(
        transition_matrices=[1],
        observation_matrices=[1],
        initial_state_mean=0,
        initial_state_covariance=1,
        observation_covariance=1,
        transition_covariance=0.01
    )
    state_means, _ = kf.filter(observations)
    return state_means.flatten()  # time-varying beta


def spread_and_z_score(x, y, beta):
    spread = y - x * beta
    mu = spread.rolling(window=100, min_periods=10).mean()
    sigma = spread.rolling(window=100, min_periods=10).std()
    z = (spread - mu) / sigma
    return spread, z


def adf_test(series):
    series = series.dropna()
    res = adfuller(series)
    return {
        "adf_stat": res[0], 
        "pvalue": res[1], 
        "usedlags": res[2], 
        "nobs": res[3]
    }


def rolling_corr(x, y, window=60):
    return x.rolling(window).corr(y)


def backtest_mean_reversion(z_scores, entry_threshold=2, exit_threshold=0):
    position = 0
    positions = []

    for zscore in z_scores:
        if zscore > entry_threshold:
            position = -1  # Short spread
        elif zscore < exit_threshold:
            position = 0   # Exit
        positions.append(position)
    
    return pd.Series(positions, index=z_scores.index)

from sqlalchemy import text
import pandas as pd

def get_price_series(symbol, engine):

    query = text("""
        SELECT ts, price FROM ticks
        WHERE symbol = :symbol
        ORDER BY ts ASC
    """)
    
    df = pd.read_sql(query, engine, params={"symbol": symbol})
    df.set_index("ts", inplace=True)
    
    return df["price"]

def get_full_df(symbol, engine):

    query = text("""
        SELECT ts, price,qty FROM ticks
        WHERE symbol = :symbol
        ORDER BY ts ASC
    """)
    
    df = pd.read_sql(query, engine, params={"symbol": symbol})
    # df.set_index("ts", inplace=True)
    
    return df


# 9. Full Analytics in One Call
def full_pair_analytics(symbol1, symbol2, engine, window=60):
    # Get price series from DB
    px_df = get_full_df(symbol1, engine)  
    py_df = get_full_df(symbol2, engine)
    print(px_df.columns)
    px_df = px_df.drop_duplicates(subset='ts', keep='last')
    py_df = py_df.drop_duplicates(subset='ts', keep='last')

    px = px_df.set_index('ts')['price']
    py = py_df.set_index('ts')['price'] 



    # Align time series (same timestamps)
    data = pd.concat([px, py], axis=1).dropna()
    px, py = data.iloc[:, 0], data.iloc[:, 1]

    # OLS regression to compute hedge ratio (beta)
    beta, intercept, _ = ols_ratio(px, py)

    # Compute spread and z-score
    spread, z = spread_and_z_score(px, py, beta)

    # Rolling correlation
    rolling_corr_series = rolling_corr(px, py, window=window)

    # ADF test (for stationarity of spread)
    adf_results = adf_test(spread)
    
    x_stats = stats(px_df)
    y_stats = stats(py_df)

    analytics = {
        'beta': beta,
        'intercept': intercept,
        'latest_spread': spread.iloc[-1],
        'latest_zscore': z.iloc[-1],
        'adf': adf_results,
        'rolling_corr': rolling_corr_series,
        'spread': spread,
        'zscore': z,
        'x_stats': x_stats,
        'y_stats': y_stats,  
    }

    # Backtest
    positions = backtest_mean_reversion(z)
    spread_returns = spread.diff().fillna(0)
    strategy_returns = (positions.shift(1) * spread_returns).fillna(0)

    analytics.update({
        "positions": positions,
        "strategy_returns": strategy_returns,
        "cumulative_return": (1 + strategy_returns).cumprod().iloc[-1] - 1,
        "latest_position": positions.iloc[-1],
    })


    return analytics
