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
    BUY = 'buy'
    SELL = 'sell'

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
            
    def create_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        params: Dict = None
    ) -> Dict:
        """
        创建订单
        """
        try:
            # 准备订单参数
            order_params = self._prepare_order_params(
                symbol, order_type, side, amount, price, stop_price, params
            )
            
            # 执行订单
            order = self.exchange.create_order(**order_params)
            
            # 存储订单信息
            self.orders[order['id']] = {
                'order': order,
                'status': OrderStatus.OPEN,
                'created_at': datetime.now(),
                'updates': []
            }
            
            self._pending_orders.append(order['id'])
            self.logger.info(f"Order created: {order['id']}")
            
            return order
            
        except Exception as e:
            self.logger.error(f"Error creating order: {str(e)}")
            raise
            
    def _prepare_order_params(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        params: Dict = None
    ) -> Dict:
        order_params = {
            'symbol': self.exchange.market_id(symbol),
            'type': order_type.value,
            'side': side.value,
            'amount': float(amount)
        }
        
        # 合并额外参数
        if params:
            order_params['params'] = params
            
        if price and order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            order_params['price'] = float(price)
            
        # 对于止损单和止损限价单，添加触发价格
        if stop_price and order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if 'params' not in order_params:
                order_params['params'] = {}
            order_params['params']['stopPrice'] = float(stop_price)
            
        return order_params
        
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
            if position and float(position['positionAmt']) != 0:
                side = OrderSide.SELL if float(position['positionAmt']) > 0 else OrderSide.BUY
                amount = abs(float(position['positionAmt']))
                
                return self.create_order(
                    symbol=symbol,
                    order_type=OrderType.MARKET,
                    side=side,
                    amount=amount
                )
                
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
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
