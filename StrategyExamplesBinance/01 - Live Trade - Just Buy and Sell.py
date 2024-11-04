import datetime as dt
import backtrader as bt
from backtrader_binance import BinanceStore
from ConfigBinance.Config import Config  # Configuration file

"""
这是一个简单的买卖策略示例，主要逻辑如下:

1. 策略初始化:
   - 创建orders字典用于跟踪每个交易对的订单状态
   - 每个交易对初始订单状态为None

2. 交易逻辑(next函数):
   - 遍历所有交易对的最新K线数据
   - 打印每根K线的OHLCV信息
   - 仅在实时交易模式下执行以下逻辑:
     a. 检查当前持仓
     b. 如果有持仓且没有未完成的卖出订单,则可以考虑卖出
     c. 如果没有持仓且没有未完成的买入订单,则可以考虑买入

3. 订单管理:
   - 使用self.orders字典记录每个交易对的订单
   - 避免重复下单,确保一个交易对同时只有一个活跃订单
   - 订单完成后更新订单状态

4. 风险控制:
   - 在下单前检查账户余额
   - 确保订单状态正常
   - 避免过度交易
"""

# Trading System
class JustBuySellStrategy(bt.Strategy):
    """
    Live strategy demonstration - just buy and sell
    """
    params = (  # Parameters of the trading system
        ('coin_target', ''),
    )

    def __init__(self):
        """Initialization, adding indicators for each ticker"""
        self.orders = {}  # All orders as a dict, for this particularly trading strategy one ticker is one order
        for d in self.datas:  # Running through all the tickers
            self.orders[d._name] = None  # There is no order for ticker yet

    def next(self):
        """Arrival of a new ticker candle"""
        for data in self.datas:  # Running through all the requested bars of all tickers
            ticker = data._name
            status = data._state  # 0 - Live data, 1 - History data, 2 - None
            _interval = self.broker._store.get_interval(data._timeframe, data._compression)

            if status in [0, 1]:
                if status: _state = "False - History data"
                else: _state = "True - Live data"

                print('{} / {} [{}] - Open: {}, High: {}, Low: {}, Close: {}, Volume: {} - Live: {}'.format(
                    bt.num2date(data.datetime[0]).strftime('%Y-%m-%d %H:%M:%S'),
                    data._name,
                    _interval,  # ticker timeframe
                    data.open[0],
                    data.high[0],
                    data.low[0],
                    data.close[0],
                    data.volume[0],
                    _state,
                ))

                if status == 0:  # Live trade
                    symbol_balance, short_symbol_name = self.broker._store.get_symbol_balance(ticker)
                    
                    # 检查是否有持仓
                    if symbol_balance > 0:
                        print(f"Found position: {symbol_balance} {short_symbol_name}")
                        
                        try:
                            # 获取可用余额
                            available_balance = self.broker._store.get_available_balance(ticker)
                            print(f"Available balance: {available_balance} {short_symbol_name}")
                            
                            if available_balance <= 0:
                                print(f"No available balance to sell for {ticker}")
                                return
                                
                            # 使用更小的数量（例如95%）
                            sell_size = min(symbol_balance, available_balance) * 0.95
                            # 格式化数量，确保符合交易所规则
                            sell_size = float(self.broker._store.format_quantity(ticker, sell_size))
                            
                            if sell_size <= 0:
                                print(f"Invalid sell size: {sell_size}")
                                return
                                
                            print(f" - sell {ticker} size = {sell_size} at Market price")
                            self.orders[data._name] = self.sell(
                                data=data,
                                exectype=bt.Order.Market,
                                size=sell_size
                            )
                            print(f"\t - The Market order has been submitted {self.orders[data._name].binance_order['orderId']} to sell {data._name}")
                            
                        except Exception as e:
                            print(f"Error creating sell order: {str(e)}")
                            import traceback
                            traceback.print_exc()
                        return
                        
                    # 如果没有持仓，执行原来的买入逻辑
                    print(f"\t - Free balance: {self.broker.getcash()} {self.p.coin_target}")
                    print(f"\t - {ticker} current balance = {symbol_balance} {short_symbol_name}")

                    if not self.getposition(data):
                        print("there is no position")
                        
                        # 检查是否有未完成的买入订单
                        order = self.orders[data._name]
                        if order and order.status == bt.Order.Accepted:
                            print(f"\t - Cancel the order {order.binance_order['orderId']} to buy {data._name}")
                            self.cancel(order)

                        # 买入逻辑
                        size = 0.005  # 约等于 12.5 USDT
                        current_price = data.close[0]
                        
                        print(f" - buy {ticker} size = {size} at Market price (estimated value: {size * current_price:.2f} USDT)")
                        self.orders[data._name] = self.buy(data=data, exectype=bt.Order.Market, size=size)
                        print(f"\t - The Market order has been submitted {self.orders[data._name].binance_order['orderId']} to buy {data._name}")

    def notify_order(self, order):
        """Changing the status of the order"""
        order_data_name = order.data._name  # Name of ticker from order
        self.log(f'Order number {order.ref} {order.info["order_number"]} {order.getstatusname()} {"Buy" if order.isbuy() else "Sell"} {order_data_name} {order.size} @ {order.price}')
        if order.status == bt.Order.Completed:  # If the order is fully executed
            if order.isbuy():  # The order to buy
                self.log(f'Buy {order_data_name} Price: {order.executed.price:.2f}, Value {order.executed.value:.2f} {self.p.coin_target}, Commission {order.executed.comm:.10f} {self.p.coin_target}')
            else:  # The order to sell
                self.log(f'Sell {order_data_name} Price: {order.executed.price:.2f}, Value {order.executed.value:.2f} {self.p.coin_target}, Commission {order.executed.comm:.10f} {self.p.coin_target}')
            self.orders[order_data_name] = None  # Reset the order to enter the position

    def notify_trade(self, trade):
        """Changing the position status"""
        if trade.isclosed:  # If the position is closed
            self.log(f'Profit on a closed position {trade.getdataname()} Total={trade.pnl:.2f}, No commission={trade.pnlcomm:.2f}')

    def log(self, txt, dt=None):
        """Print string with date to the console"""
        dt = bt.num2date(self.datas[0].datetime[0]) if not dt else dt  # date or date of the current bar
        print(f'{dt.strftime("%d.%m.%Y %H:%M")}, {txt}')  # Print the date and time with the specified text to the console


if __name__ == '__main__':
    cerebro = bt.Cerebro(quicknotify=True)

    coin_target = 'USDT'  # the base ticker in which calculations will be performed
    symbol = 'ETH' + coin_target  # the ticker by which we will receive data in the format <CodeTickerBaseTicker>

    store = BinanceStore(
        api_key=Config.BINANCE_API_KEY,
        api_secret=Config.BINANCE_API_SECRET,
        coin_target=coin_target,
        testnet=False)  # Binance Storage

    # live connection to Binance - for Offline comment these two lines
    broker = store.getbroker()
    cerebro.setbroker(broker)

    # Historical 1-minute bars for the last hour + new live bars / timeframe M1
    from_date = dt.datetime.utcnow() - dt.timedelta(minutes=5)
    data = store.getdata(timeframe=bt.TimeFrame.Minutes, compression=1, dataname=symbol, start_date=from_date, LiveBars=True)

    cerebro.adddata(data)  # Adding data

    cerebro.addstrategy(JustBuySellStrategy, coin_target=coin_target)  # Adding a trading system

    cerebro.run()  # Launching a trading system
    cerebro.plot()  # Draw a chart
