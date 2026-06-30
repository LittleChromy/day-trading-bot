import alpaca_trade_api as tradeapi
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from config import Config

logger = logging.getLogger(__name__)

class AlpacaDataHandler:
    """Handles all data retrieval from Alpaca API"""
    
    def __init__(self):
        self.api = tradeapi.REST(
            Config.ALPACA_API_KEY,
            Config.ALPACA_SECRET_KEY,
            Config.ALPACA_BASE_URL,
            api_version='v2'
        )
        self.data_cache = {}
    
    def get_bars(self, symbol, timeframe='1min', limit=1000):
        """
        Get historical bar data for a symbol
        timeframe: '1min', '5min', '15min', '1H', '1D'
        """
        try:
            bars = self.api.get_bars(symbol, timeframe, limit=limit)
            df = bars.df
            return df
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {str(e)}")
            return None
    
    def get_latest_price(self, symbol):
        """
        Get the latest price for a symbol
        """
        try:
            quote = self.api.get_latest_quote(symbol)
            return quote.bid if quote else None
        except Exception as e:
            logger.error(f"Error fetching latest price for {symbol}: {str(e)}")
            return None
    
    def get_latest_trades(self, symbol):
        """
        Get latest trade data
        """
        try:
            trade = self.api.get_latest_trade(symbol)
            return trade
        except Exception as e:
            logger.error(f"Error fetching latest trade for {symbol}: {str(e)}")
            return None
    
    def get_account_info(self):
        """
        Get account information
        """
        try:
            account = self.api.get_account()
            return account
        except Exception as e:
            logger.error(f"Error fetching account info: {str(e)}")
            return None
    
    def get_positions(self):
        """
        Get current positions
        """
        try:
            positions = self.api.list_positions()
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            return []
    
    def get_multiple_bars(self, symbols, timeframe='1min', limit=500):
        """
        Get bars for multiple symbols at once
        """
        data = {}
        for symbol in symbols:
            bars = self.get_bars(symbol, timeframe, limit)
            if bars is not None:
                data[symbol] = bars
        return data
    
    def prepare_data(self, df):
        """
        Prepare and clean data for strategy analysis
        """
        if df is None or df.empty:
            return None
        
        df = df.copy()
        df = df.sort_index()
        return df
