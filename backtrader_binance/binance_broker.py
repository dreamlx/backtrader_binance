import datetime as dt

from collections import defaultdict, deque
from math import copysign

from backtrader.broker import BrokerBase
from backtrader.order import Order, OrderBase
from backtrader.position import Position
from binance.enums import *


class BinanceOrder(OrderBase):
    def __init__(self, owner, data, exectype, binance_order):
        # 设置基本属性
        self.owner = owner
        self.data = data
        self.exectype = exectype
        self.binance_order = binance_order
        
        # 设置订单大小和类型
        self.size = float(binance_order['origQty'])
        self.ordtype = self.Buy if binance_order['side'] == 'BUY' else self.Sell
        
        # 现在调用父类构造函数
        super(BinanceOrder, self).__init__()
        
        # 初始化价格（后续可能会更新）
        self.price = float(binance_order.get('price', data.close[0]))
        
        # 设置订单状态
        if binance_order['status'] == 'FILLED':
            self.status = Order.Completed
            self.executed = self.size
        elif binance_order['status'] == 'NEW':
            self.status = Order.Submitted
        elif binance_order['status'] == 'PARTIALLY_FILLED':
            self.status = Order.Partial
        elif binance_order['status'] in ['CANCELED', 'REJECTED', 'EXPIRED']:
            self.status = Order.Canceled
        else:
            self.status = Order.Created
        
        # 设置订单ID和其他信息
        self.info = {
            'order_number': binance_order['orderId'],
            'status': binance_order['status'],
        }
        
        # 设置创建时间
        self.created = binance_order.get('transactTime', None)


class BinanceBroker(BrokerBase):
    _ORDER_TYPES = {
        Order.Limit: ORDER_TYPE_LIMIT,
        Order.Market: ORDER_TYPE_MARKET,
        Order.Stop: ORDER_TYPE_STOP_LOSS,
        Order.StopLimit: ORDER_TYPE_STOP_LOSS_LIMIT,
    }

    def __init__(self, store):
        super(BinanceBroker, self).__init__()

        self.notifs = deque()
        self.positions = defaultdict(Position)

        self.startingcash = self.cash = 0  # Стартовые и текущие свободные средства по счету
        self.startingvalue = self.value = 0  # Стартовая и текущая стоимость позиций

        self.open_orders = list()
    
        self._store = store
        self._store.binance_socket.start_user_socket(self._handle_user_socket_message)

    def start(self):
        self.startingcash = self.cash = self.getcash()  # Стартовые и текущие свободные средства по счету. Подписка на позиции для портфеля/биржи
        self.startingvalue = self.value = self.getvalue()  # Стартовая и текущая стоимость позиций

    def _execute_order(self, order, date, executed_size, executed_price, executed_value, executed_comm):
        order.execute(
            date,
            executed_size,
            executed_price,
            0, executed_value, executed_comm,
            0, 0.0, 0.0,
            0.0, 0.0,
            0, 0.0)
        pos = self.getposition(order.data, clone=False)
        pos.update(copysign(executed_size, order.size), executed_price)

    def _handle_user_socket_message(self, msg):
        """https://binance-docs.github.io/apidocs/spot/en/#payload-order-update"""
        # print(msg)
        # {'e': 'executionReport', 'E': 1707120960762, 's': 'ETHUSDT', 'c': 'oVoRofmTTXJCqnGNuvcuEu', 'S': 'BUY', 'o': 'MARKET', 'f': 'GTC', 'q': '0.00220000', 'p': '0.00000000', 'P': '0.00000000', 'F': '0.00000000', 'g': -1, 'C': '', 'x': 'NEW', 'X': 'NEW', 'r': 'NONE', 'i': 15859894465, 'l': '0.00000000', 'z': '0.00000000', 'L': '0.00000000', 'n': '0', 'N': None, 'T': 1707120960761, 't': -1, 'I': 33028455024, 'w': True, 'm': False, 'M': False, 'O': 1707120960761, 'Z': '0.00000000', 'Y': '0.00000000', 'Q': '0.00000000', 'W': 1707120960761, 'V': 'EXPIRE_MAKER'}

        # {'e': 'executionReport', 'E': 1707120960762, 's': 'ETHUSDT', 'c': 'oVoRofmTTXJCqnGNuvcuEu', 'S': 'BUY', 'o': 'MARKET', 'f': 'GTC', 'q': '0.00220000', 'p': '0.00000000', 'P': '0.00000000', 'F': '0.00000000', 'g': -1, 'C': '',
        # 'x': 'TRADE', 'X': 'FILLED', 'r': 'NONE', 'i': 15859894465, 'l': '0.00220000', 'z': '0.00220000', 'L': '2319.53000000', 'n': '0.00000220', 'N': 'ETH', 'T': 1707120960761, 't': 1297224255, 'I': 33028455025, 'w': False,
        # 'm': False, 'M': True, 'O': 1707120960761, 'Z': '5.10296600', 'Y': '5.10296600', 'Q': '0.00000000', 'W': 1707120960761, 'V': 'EXPIRE_MAKER'}
        if msg['e'] == 'executionReport':
            if msg['s'] in self._store.symbols:
                for o in self.open_orders:
                    if o.binance_order['orderId'] == msg['i']:
                        if msg['X'] in [ORDER_STATUS_FILLED, ORDER_STATUS_PARTIALLY_FILLED]:
                            _dt = dt.datetime.fromtimestamp(int(msg['T']) / 1000)
                            executed_size = float(msg['l'])
                            executed_price = float(msg['L'])
                            executed_value = float(msg['Z'])
                            executed_comm = float(msg['n'])
                            # print(_dt, executed_size, executed_price)
                            self._execute_order(o, _dt, executed_size, executed_price, executed_value, executed_comm)
                        self._set_order_status(o, msg['X'])

                        if o.status not in [Order.Accepted, Order.Partial]:
                            self.open_orders.remove(o)
                        self.notify(o)
        elif msg['e'] == 'error':
            raise msg
    
    def _set_order_status(self, order, binance_order_status):
        if binance_order_status == ORDER_STATUS_CANCELED:
            order.cancel()
        elif binance_order_status == ORDER_STATUS_EXPIRED:
            order.expire()
        elif binance_order_status == ORDER_STATUS_FILLED:
            order.completed()
        elif binance_order_status == ORDER_STATUS_PARTIALLY_FILLED:
            order.partial()
        elif binance_order_status == ORDER_STATUS_REJECTED:
            order.reject()

    def _submit(self, owner, data, side, exectype, size, price):
        symbol = data._name
        type = 'MARKET' if exectype == Order.Market else 'LIMIT'
        binance_order = self._store.create_order(symbol, side, type, size, price)
        
        # 创建订单对象
        order = BinanceOrder(owner, data, exectype, binance_order)
        
        # 如果是市价单且订单状态为FILLED，尝试获取成交信息
        if type == 'MARKET' and binance_order['status'] == 'FILLED':
            try:
                # 获取订单的成交信息
                trades = self._store.binance.get_my_trades(symbol=symbol, orderId=binance_order['orderId'])
                if trades:
                    # 计算平均成交价格
                    total_qty = sum(float(trade['qty']) for trade in trades)
                    total_price = sum(float(trade['price']) * float(trade['qty']) for trade in trades)
                    avg_price = total_price / total_qty if total_qty > 0 else price
                    order.price = avg_price
            except Exception as e:
                print(f"Warning: Could not fetch trade details: {str(e)}")
                # 如果无法获取成交信息，使用当前价格
                order.price = data.close[0]
        
        # 更新订单状态
        self.orders.append(order)
        
        if order.status == Order.Completed:
            pos = self.getposition(data)
            if pos:
                pos.update(order.size, order.price)
            else:
                self.positions[data._name] = Position(order.size, order.price)
        
        return order

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None,
            **kwargs):
        return self._submit(owner, data, SIDE_BUY, exectype, size, price)

    def cancel(self, order):
        order_id = order.binance_order['orderId']
        symbol = order.binance_order['symbol']
        self._store.cancel_order(symbol=symbol, order_id=order_id)
        
    def format_price(self, value):
        return self._store.format_price(value)

    def get_asset_balance(self, asset):
        return self._store.get_asset_balance(asset)

    def getcash(self):
        self.cash = self._store._cash
        return self.cash

    def get_notification(self):
        if not self.notifs:
            return None

        return self.notifs.popleft()

    def getposition(self, data, clone=True):
        pos = self.positions[data._dataname]
        if clone:
            pos = pos.clone()
        return pos

    def getvalue(self, datas=None):
        self.value = self._store._value
        return self.value

    def notify(self, order):
        self.notifs.append(order)

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None,
             **kwargs):
        return self._submit(owner, data, SIDE_SELL, exectype, size, price)
