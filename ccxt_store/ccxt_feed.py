from typing import Optional, Dict, Any
import pandas as pd
from datetime import datetime, timedelta
import time

class CCXTFeed:
    """
    CCXT数据馈送类
    处理实时和历史数据的获取和处理
    """
    def __init__(
        self,
        store,
        symbol: str,
        timeframe: str = '1m',
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        live: bool = False
    ):
        self.store = store
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date
        self.live = live
        
        self._current_data = None
        self._last_timestamp = None
        
    def start(self):
        """启动数据馈送"""
        if not self.live:
            # 获取历史数据
            self._current_data = self.store.get_historical_data(
                self.symbol,
                self.timeframe,
                self.start_date,
                None
            )
        else:
            # 获取最近的数据作为起点
            self._current_data = self.store.get_historical_data(
                self.symbol,
                self.timeframe,
                datetime.now() - timedelta(minutes=5),
                None
            )
            self._last_timestamp = self._current_data.iloc[-1]['timestamp']
            
    def _get_new_data(self) -> Optional[Dict[str, Any]]:
        """获取新数据"""
        if not self.live:
            return None
            
        try:
            new_data = self.store.get_historical_data(
                self.symbol,
                self.timeframe,
                self._last_timestamp,
                2  # 获取最新的1-2根K线
            )
            
            if not new_data.empty and new_data.iloc[-1]['timestamp'] > self._last_timestamp:
                self._last_timestamp = new_data.iloc[-1]['timestamp']
                return new_data.iloc[-1].to_dict()
                
        except Exception as e:
            print(f"Error getting new data: {str(e)}")
            
        return None
