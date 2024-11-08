from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime
import time
import logging

class OrderType(Enum):
    MARKET = 'market'
    LIMIT = 'limit'
    STOP = 'stop'
    STOP_LIMIT = 'stop_limit'

class OrderSide(Enum):
    BUY = 'BUY'
    SELL = 'SELL'

class OrderStatus(Enum):
    PENDING = 'pending'
    OPEN = 'open'
    CLOSED = 'closed'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
    EXPIRED = 'expired'

class CCXTBroker:
    """
    CCXT Broker类 - 处理订单执行和仓位管理
    """
    def __init__(
        self,
        store,
        leverage: int = 50,
        margin_mode: str = 'cross',
        default_type: str = 'future'
    ):
        self.store = store
        self.exchange = store.exchange
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.default_type = default_type
        
        # 初始化存储
        self.orders: Dict[str, Dict] = {}  # 订单存储
        self.positions: Dict[str, Dict] = {}  # 仓位存储
        self._pending_orders: List[str] = []  # 待处理订单
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
        # 初始化交易设置
        self._initialize_trading_settings()
        
    def _initialize_trading_settings(self):
        """初始化交易设置（杠杆、保证金模式等）"""
        try:
            if self.default_type == 'future':
                # 获取所有交易对的列表
                markets = self.exchange.load_markets()
                
                # 遍历所有交易对
                for symbol in self.store.symbols:
                    try:
                        # 设置杠杆
                        self.exchange.fapiPrivatePostLeverage({
                            'leverage': self.leverage,
                            'symbol': self.exchange.market_id(symbol)
                        })
                        
                        # 设置保证金模式
                        try:
                            self.exchange.fapiPrivatePostMarginType({
                                'symbol': self.exchange.market_id(symbol),
                                'marginType': self.margin_mode.upper()
                            })
                        except Exception as margin_error:
                            # 检查是否是"无需更改保证金类型"的错误
                            if '"code":-4046' in str(margin_error):
                                self.logger.info(f"Margin type already set for {symbol}")
                            else:
                                raise margin_error
                        
                        self.logger.info(f"Trading settings initialized for {symbol}: leverage={self.leverage}, margin_mode={self.margin_mode}")
                    except Exception as e:
                        self.logger.error(f"Error initializing trading settings for {symbol}: {str(e)}")
                        raise
                        
        except Exception as e:
            self.logger.error(f"Error initializing trading settings: {str(e)}")
            raise
            
    def create_order(self, symbol: str, order_type: OrderType, side: OrderSide, amount: float):
        try:
            # 详细的参数日志
            self.logger.debug(f"Creating order with raw parameters:")
            self.logger.debug(f"- Symbol: {symbol}")
            self.logger.debug(f"- Order Type: {order_type}, Type: {type(order_type)}")
            self.logger.debug(f"- Side: {side}, Type: {type(side)}")
            self.logger.debug(f"- Amount: {amount}")
            
            # 确保 side 是正确的格式
            if isinstance(side, OrderSide):
                side_str = side.value
            else:
                side_str = str(side).upper()
                
            self.logger.debug(f"Processed side parameter: {side_str}")
            
            # 验证 side 参数
            if side_str not in ['BUY', 'SELL']:
                raise ValueError(f"Invalid side value: {side_str}")
                
            order_params = {
                'symbol': self.exchange.market_id(symbol),
                'side': side_str,
                'type': order_type.value.upper() if hasattr(order_type, 'value') else str(order_type).upper(),
                'quantity': str(amount)
            }
            
            self.logger.debug(f"Final order parameters: {order_params}")
            return self.exchange.fapiPrivatePostOrder(order_params)
            
        except Exception as e:
            self.logger.error(f"Error creating order: {str(e)}")
            self.logger.error(f"Failed parameters: {order_params}")
            raise
            
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> Dict:
        """取消订单"""
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            
            if order_id in self.orders:
                self.orders[order_id]['status'] = OrderStatus.CANCELED
                self.orders[order_id]['updates'].append({
                    'time': datetime.now(),
                    'status': OrderStatus.CANCELED
                })
                
            if order_id in self._pending_orders:
                self._pending_orders.remove(order_id)
                
            self.logger.info(f"Order canceled: {order_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error canceling order: {str(e)}")
            raise
            
    def get_order(self, order_id: str, symbol: Optional[str] = None) -> Dict:
        """获取订单信息"""
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            
            # 更新本地订单状态
            if order_id in self.orders:
                self.orders[order_id]['order'] = order
                self.orders[order_id]['updates'].append({
                    'time': datetime.now(),
                    'status': order['status']
                })
                
            return order
            
        except Exception as e:
            self.logger.error(f"Error fetching order: {str(e)}")
            raise
            
    def get_position(self, symbol: str) -> Dict:
        """获取持仓信息"""
        try:
            if self.default_type == 'future':
                positions = self.exchange.fapiPrivateV2GetPositionRisk()
                position = next(
                    (pos for pos in positions if pos['symbol'] == symbol.replace('/', '')),
                    None
                )
                
                if position:
                    self.positions[symbol] = position
                    
                return position
                
        except Exception as e:
            self.logger.error(f"Error fetching position: {str(e)}")
            raise
            
    def get_account_balance(self) -> Dict:
        """获取账户余额"""
        try:
            if self.default_type == 'future':
                return self.exchange.fapiPrivateV2GetAccount()
            return self.exchange.fetch_balance()
            
        except Exception as e:
            self.logger.error(f"Error fetching balance: {str(e)}")
            raise
            
    def update_pending_orders(self):
        """更新待处理订单状态"""
        for order_id in self._pending_orders[:]:  # 创建副本进行迭代
            try:
                order = self.get_order(order_id)
                if order['status'] not in ['open', 'pending']:
                    self._pending_orders.remove(order_id)
                    
            except Exception as e:
                self.logger.error(f"Error updating order {order_id}: {str(e)}")
                
    def close_position(self, symbol: str) -> Optional[Dict]:
        """关闭持仓"""
        try:
            position = self.get_position(symbol)
            self.logger.debug(f"Current position for {symbol}: {position}")
            
            if position and float(position['positionAmt']) != 0:
                position_amt = float(position['positionAmt'])
                side = OrderSide.SELL if position_amt > 0 else OrderSide.BUY
                amount = abs(position_amt)
                
                self.logger.info(f"Closing position for {symbol}")
                self.logger.info(f"Position amount: {position_amt}")
                self.logger.info(f"Close side: {side}")
                self.logger.info(f"Close amount: {amount}")
                
                return self.create_order(
                    symbol=symbol,
                    order_type=OrderType.MARKET,
                    side=side,
                    amount=amount
                )
            else:
                self.logger.info(f"No position to close for {symbol}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
            self.logger.error(f"Position details: {position if 'position' in locals() else 'Not available'}")
            raise

    def get_available_balance(self) -> float:
        """获取可用余额"""
        try:
            if self.default_type == 'future':
                account = self.exchange.fapiPrivateV2GetAccount()
                # 获取USDT资产
                usdt_asset = next(
                    (asset for asset in account['assets'] if asset['asset'] == 'USDT'),
                    None
                )
                if usdt_asset:
                    return float(usdt_asset['availableBalance'])
                return 0.0
        except Exception as e:
            self.logger.error(f"Error getting available balance: {str(e)}")
            return 0.0

    def add_position_margin(self, symbol: str, amount: float) -> bool:
        """追加逐仓保证金"""
        try:
            self.exchange.fapiPrivatePostPositionMargin({
                'symbol': self.exchange.market_id(symbol),
                'amount': str(amount),
                'type': 1,  # 1: 追加保证金
                'positionSide': 'BOTH'
            })
            self.logger.info(f"Added {amount} USDT margin to position {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding position margin: {str(e)}")
            return False

    def transfer_to_isolated_margin(self, symbol: str, amount: float) -> bool:
        """将资金转入逐仓保证金账户"""
        try:
            # 转移资金到逐仓保证金账户
            self.exchange.fapiPrivatePostPositionMargin({
                'symbol': self.exchange.market_id(symbol),
                'amount': str(amount),
                'type': 1,  # 1: 转入; 2: 转出
                'positionSide': 'BOTH'  # 双向持仓模式
            })
            self.logger.info(f"Transferred {amount} USDT to isolated margin for {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Error transferring to isolated margin: {str(e)}")
            return False

    def transfer_margin_to_isolated(self, symbol: str, amount: float):
        try:
            self.exchange.fapiPrivatePostMarginType({
                'symbol': symbol,
                'amount': str(amount),
                'type': 'MARGIN_TRANSFER'
            })
        except Exception as e:
            self.logger.error(f"Error transferring margin: {str(e)}")

    def get_isolated_margin_balance(self, symbol: str) -> float:
        try:
            position = self.get_position(symbol)
            if position:
                return float(position['isolatedWallet'])
            return 0.0
        except Exception as e:
            self.logger.error(f"Error getting isolated margin: {str(e)}")
            return 0.0

    def validate_order_params(self, params: dict) -> bool:
        """验证订单参数"""
        if 'side' not in params:
            return False
        if params['side'] not in ['BUY', 'SELL']:
            return False
        return True
