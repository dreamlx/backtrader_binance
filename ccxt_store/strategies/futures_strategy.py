from typing import Dict, Optional
from datetime import datetime
import time
import logging

from ccxt_store.ccxt_broker import CCXTBroker, OrderType, OrderSide

MIN_NOTIONAL_SAFETY_FACTOR = 1.5  # 增加到1.5

class FuturesStrategy:
    """
    基于CCXT的期货空单策略
    """
    def __init__(
        self,
        broker: CCXTBroker,
        symbols: list,
        leverage: int = 50,
        min_position_value: float = 50,  # 最小仓位价值
    ):
        self.broker = broker
        self.symbols = symbols
        self.leverage = leverage
        self.min_position_value = min_position_value
        
        # 验证最小仓位价值
        for symbol in symbols:
            market = broker.exchange.market(symbol)
            min_notional = max(10.0, float(market['limits']['cost']['min']))
            if min_position_value < min_notional:
                raise ValueError(f"min_position_value ({min_position_value}) must be greater than minimum notional ({min_notional}) for {symbol}")
        
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
                # 打印市场信息
                market = self.broker.exchange.market(symbol)
                self.logger.info(f"Market info for {symbol}:")
                self.logger.info(f"- Minimum amount: {market['limits']['amount']['min']}")
                self.logger.info(f"- Minimum cost: {market['limits']['cost']['min']}")
                self.logger.info(f"- Amount precision: {market['precision']['amount']}")
                self.logger.info(f"- Price precision: {market['precision']['price']}")
                
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
            # 获取市场信息
            market = self.broker.exchange.market(symbol)
            min_qty = float(market['limits']['amount']['min'])
            
            # 使用更高的最小名义价值
            min_notional = max(10.0, float(market['limits']['cost']['min']))
            
            # 获取精度
            precision_str = str(market['precision']['amount'])
            # 计算小数位数
            if '.' in precision_str:
                precision = len(precision_str.split('.')[-1])
            else:
                precision = int(precision_str)
            
            # 计算最小需要的数量以满足最小名义价值
            min_required_qty = min_notional / current_price
            
            # 计算目标数量（基于目标仓位价值）
            target_value_qty = self.min_position_value / current_price
            
            # 选择更大的数量，并按精度处理
            target_qty = round(max(
                target_value_qty,
                min_required_qty,
                min_qty
            ), precision)
            
            # 计算实际下单价值
            position_value = target_qty * current_price
            
            # 计算所需保证金（考虑初始保证金和维持保证金）
            initial_margin_rate = 0.02  # 2% initial margin rate for 50x leverage
            maintenance_margin_rate = 0.005  # 0.5% maintenance margin
            
            # 计算所需的总保证金
            required_margin = (position_value * initial_margin_rate) * MIN_NOTIONAL_SAFETY_FACTOR
            maintenance_margin = position_value * maintenance_margin_rate
            total_required_margin = required_margin + maintenance_margin
            
            # 获取可用余额
            available_balance = self.broker.get_available_balance()
            
            # 添加保证金相关的日志
            self.logger.info(f"Margin calculations:")
            self.logger.info(f"- Initial margin required: {required_margin} USDT")
            self.logger.info(f"- Maintenance margin: {maintenance_margin} USDT")
            self.logger.info(f"- Total margin required: {total_required_margin} USDT")
            self.logger.info(f"- Available balance: {available_balance} USDT")
            
            if available_balance < total_required_margin:
                self.logger.warning(f"Insufficient balance. Required: {total_required_margin} USDT, Available: {available_balance} USDT")
                return
                
            # 最后验证名义价值
            if position_value < min_notional:
                self.logger.warning(f"Position value {position_value} USDT is still less than minimum notional {min_notional} USDT")
                return
                
            # 计算完 total_required_margin 后，先转入保证金
            if self.broker.margin_mode.lower() == 'isolated':
                transfer_amount = total_required_margin * 1.1  # 多转 10% 作为缓冲
                success = self.broker.transfer_to_isolated_margin(symbol, transfer_amount)
                if not success:
                    self.logger.error("Failed to transfer margin to isolated account")
                    return
                
            self.logger.info(f"Attempting to open short position with quantity: {target_qty} (Value: {position_value} USDT)")
            
            # 创建订单
            order = self.broker.create_order(
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=OrderSide.SELL,
                amount=target_qty
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

    # 从现货账户转入合约账户
    def transfer_to_futures_account(self, amount: float, currency: str = 'USDT') -> bool:
        try:
            self.exchange.sapi_post_futures_transfer({
                'asset': currency,
                'amount': amount,
                'type': 1  # 1：现货转资金账户
            })
            self.logger.info(f"Transferred {amount} {currency} to futures account")
            return True
        except Exception as e:
            self.logger.error(f"Error transferring to futures account: {str(e)}")
            return False

    def get_isolated_margin_balance(self, symbol: str) -> float:
        try:
            position = self.broker.get_position(symbol)
            if position:
                return float(position['isolatedWallet'])
            return 0.0
        except Exception as e:
            self.logger.error(f"Error getting isolated margin balance: {str(e)}")
            return 0.0

    def check_available_margin(self, symbol: str) -> float:
        if self.margin_mode.lower() == 'isolated':
            return self.get_isolated_margin_balance(symbol)
        return self.get_available_balance()
