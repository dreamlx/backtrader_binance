from datetime import datetime, timezone
import time
import ccxt
from ccxt import Exchange
import pandas as pd

class CCXTStore:
    """
    CCXT Store Class
    处理与交易所的基础连接和数据获取
    """
    def __init__(
        self,
        exchange_name: str,
        api_key: str = None,
        secret_key: str = None,
        additional_options: dict = None,
        retries: int = 3,
        symbols: list = None
    ):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.secret_key = secret_key
        self.retries = retries
        self.symbols = symbols or []
        
        # 初始化exchange
        self.exchange: Exchange = getattr(ccxt, exchange_name)({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            **(additional_options or {})
        })
        
        # 验证连接
        self._validate_connection()
        
    def _validate_connection(self):
        """验证与交易所的连接"""
        try:
            self.exchange.load_markets()
            print(f"Successfully connected to {self.exchange_name}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {self.exchange_name}: {str(e)}")
            
    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        since: datetime = None,
        limit: int = None
    ) -> pd.DataFrame:
        """获取历史K线数据"""
        try:
            # 转换时间格式
            if since is not None:
                since = int(since.replace(tzinfo=timezone.utc).timestamp() * 1000)
            
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since,
                limit=limit
            )
            
            # 转换为DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
            
        except Exception as e:
            raise Exception(f"Error fetching historical data: {str(e)}")
