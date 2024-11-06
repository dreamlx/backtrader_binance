from typing import Dict, Optional
from datetime import datetime
import time
import logging

from ccxt_store.ccxt_broker import CCXTBroker, OrderType, OrderSide

class FuturesStrategy:
    """
    基于CCXT的期货空单策略
    """
    def __init__(
        self,
        broker: CCXTBroker,
        symbols: list,
        leverage: int = 50,
        min_position_value: float = 20,  # 最小仓位价值
    ):
        self.broker = broker
        self.symbols = symbols
        self.leverage = leverage
        self.min_position_value = min_position_value
        
        # 初始化存储
        self.orders: Dict[str, Dict] = {}
        self.positions: Dict[str, Dict] = {}
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
        # 初始化策略
        self._initialize_strategy()
        
    def on_data(self, symbol: str, data: Dict):
        """
        处理新的K线数据
        """
        try:
            # 获取当前持仓
            position = self.broker.get_position(symbol)
            if position is None:
                self.logger.info(f"No position found for {symbol}")
                return
                
            position_size = float(position['positionAmt'])
            current_price = float(data['close'])
            position_value = abs(position_size * current_price)
            
            self.logger.info(f"Current position value: {position_value} USDT")
            
            # 如果仓位价值小于20 USDT，开空仓
            if position_value < self.min_position_value:
                self._open_short(symbol, current_price)
            else:
                # 平仓
                self._close_position(symbol)
                
        except Exception as e:
            self.logger.error(f"Error in on_data: {str(e)}")
            
    def _open_short(self, symbol: str, current_price: float):
        """开空仓"""
        try:
            # 计算需要的数量
            required_quantity = self.min_position_value / current_price
            
            order = self.broker.create_order(
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=OrderSide.SELL,  # 做空
                amount=required_quantity
            )
            
            self.orders[symbol] = order
            self.logger.info(f"Opening short position: {required_quantity} contracts")
            
        except Exception as e:
            self.logger.error(f"Error opening short position: {str(e)}")
            
    def _close_position(self, symbol: str):
        """平仓"""
        try:
            self.broker.close_position(symbol)
            self.logger.info(f"Closing position for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")