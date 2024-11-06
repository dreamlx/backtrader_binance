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
        
    def _initialize_strategy(self):
        """初始化策略"""
        try:
            # 获取初始持仓信息
            for symbol in self.symbols:
                position = self.broker.get_position(symbol)
                if position:
                    self.positions[symbol] = position
                    self.logger.info(f"Initial position for {symbol}: {position}")
                else:
                    self.logger.info(f"No initial position for {symbol}")
                    
        except Exception as e:
            self.logger.error(f"Error initializing strategy: {str(e)}")
        
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
                
            # 从position中获取持仓数量
            position_size = float(position.get('positionAmt', 0))
            current_price = float(data['close'])
            position_value = abs(position_size * current_price)
            
            self.logger.info(f"Current position value: {position_value} USDT")
            
            # 获取可用余额
            available_balance = self.broker.get_available_balance()
            self.logger.info(f"Available balance: {available_balance} USDT")
            
            # 如果仓位价值小于20 USDT，开空仓
            if position_value < self.min_position_value:
                # 计算需要的保证金（考虑杠杆）
                required_margin = (self.min_position_value / self.leverage) * 1.1  # 增加10%作为缓冲
                
                # 检查是否有足够的余额
                if available_balance >= required_margin:
                    # 计算需要的数量（考虑最小交易单位）
                    required_quantity = round(self.min_position_value / current_price, 3)  # 保留3位小数
                    if required_quantity > 0:
                        self._open_short(symbol, current_price)
                    else:
                        self.logger.warning(f"Calculated quantity too small: {required_quantity}")
                else:
                    self.logger.warning(f"Insufficient balance for opening position. Required: {required_margin} USDT, Available: {available_balance} USDT")
            else:
                # 平仓
                self._close_position(symbol)
                
        except Exception as e:
            self.logger.error(f"Error in on_data: {str(e)}")
            
    def _open_short(self, symbol: str, current_price: float):
        """开空仓"""
        try:
            # 获取可用余额
            available_balance = self.broker.get_available_balance()
            
            # 计算需要的保证金（考虑杠杆）
            required_margin = (self.min_position_value / self.leverage) * 1.1  # 增加10%作为缓冲
            
            if available_balance < required_margin:
                self.logger.warning(f"Insufficient balance. Required: {required_margin} USDT, Available: {available_balance} USDT")
                return
                
            # 计算需要的数量（考虑最小交易单位）
            required_quantity = round(self.min_position_value / current_price, 3)  # 保留3位小数
            
            # 添加数量检查
            if required_quantity <= 0:
                self.logger.warning(f"Calculated quantity too small: {required_quantity}")
                return
                
            self.logger.info(f"Attempting to open short position with quantity: {required_quantity}")
            
            # 创建订单
            order = self.broker.create_order(
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=OrderSide.SELL,  # 做空
                amount=required_quantity
            )
            
            self.logger.info(f"Short position opened: {order}")
            return order
            
        except Exception as e:
            self.logger.error(f"Error opening short position: {str(e)}")
            raise
            
    def _close_position(self, symbol: str):
        """平仓"""
        try:
            self.broker.close_position(symbol)
            self.logger.info(f"Closing position for {symbol}")
            
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
