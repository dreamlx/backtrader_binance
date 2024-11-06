import ccxt
import datetime as dt
import backtrader as bt
from backtrader_binance import BinanceStore
from ConfigBinance.Config import Config  # Configuration file
import time
#
# Add CCXT exchange initialization
exchange = ccxt.binance({
    'apiKey': Config.BINANCE_API_KEY,
    'secret': Config.BINANCE_API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # Use futures
        'adjustForTimeDifference': True,
        'createMarketBuyOrderRequiresPrice': False,
        'hedgeMode': False,  # 添加对冲模式设置
        'defaultNetwork': 'USDT',  # 指定默认网络
    }
})

# 添加交易所连接验证
try:
    exchange.load_markets()
    print("Successfully connected to Binance Futures")
except Exception as e:
    print(f"Failed to connect to exchange: {e}")
    exit(1)

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
   - 使用self.orders字典记录每个交易对订单
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
        ('leverage', 50),  # Set leverage to 50x
    )

    def __init__(self):
        """Initialization, adding indicators for each ticker"""
        self.orders = {}  # All orders as a dict, for this particularly trading strategy one ticker is one order
        for d in self.datas:  # Running through all the tickers
            self.orders[d._name] = None  # There is no order for ticker yet
            
        # Set leverage for each symbol
        for data in self.datas:
            try:
                symbol = data._name
                exchange.fapiPrivatePostLeverage({
                    'symbol': symbol.replace('/', ''),
                    'leverage': self.p.leverage
                })
                print(f"Leverage set to {self.p.leverage}x for {symbol}")
            except Exception as e:
                print(f"Error setting leverage: {str(e)}")

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
                    try:
                        # 使用v2版本的position risk API
                        current_position = self.get_position_info(exchange, ticker)
                        if current_position is None:
                            print(f"No position found for {ticker}")
                            return
                        current_price = data.close[0]
                        
                        if current_position:
                            position_size = float(current_position['positionAmt'])
                            unrealized_pnl = float(current_position['unRealizedProfit'])
                            
                            print(f"\nCurrent position: {position_size} {ticker}")
                            print(f"Unrealized PnL: {unrealized_pnl} USDT")
                            
                            # 止盈止损逻辑
                            if position_size != 0:
                                roi = (unrealized_pnl / (abs(position_size) * current_price)) * 100
                                if roi > 1 or roi < -0.5:
                                    order = self.close(data=data)
                                    self.orders[data._name] = order
                                    print(f"Closing position at ROI: {roi}%")
                                    time.sleep(2)
                            
                        # 开仓逻辑
                        if abs(float(current_position['positionAmt'])) < 0.001:
                            # 获取账户信息
                            account = exchange.fapiPrivateGetAccount()
                            available_balance = float(account['availableBalance'])
                            position_size_usd = min(available_balance * 0.1, 100)
                            
                            quantity = position_size_usd / current_price
                            quantity = float(self.broker._store.format_quantity(ticker, quantity))
                            
                            if quantity * current_price >= 10:
                                if data.close[0] > data.close[-1]:
                                    order = self.buy(data=data, size=quantity)
                                else:
                                    order = self.sell(data=data, size=quantity)
                                
                                self.orders[data._name] = order
                                print(f"Opening new position: {quantity} contracts")
                                time.sleep(2)
                    
                    except Exception as e:
                        print(f"Error in trading logic: {str(e)}")
                        import traceback
                        traceback.print_exc()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return  # 等待进一步的状态更新
        
        if order.status == order.Completed:
            self.handle_order_completion(order)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.handle_order_failure(order)
        
    def handle_order_completion(self, order):
        self.daily_trades += 1
        self.log(f"Order completed - {'BUY' if order.isbuy() else 'SELL'} "
                f"Price: {order.executed.price:.2f}, "
                f"Cost: {order.executed.value:.2f}, "
                f"Comm: {order.executed.comm:.2f}")
        
    def handle_order_failure(self, order):
        self.log(f"Order failed - Status: {order.getstatusname()}")
        # 重置订单状态
        self.orders[order.data._name] = None

    def notify_trade(self, trade):
        """Changing the position status"""
        if trade.isclosed:  # If the position is closed
            self.log(f'Profit on a closed position {trade.getdataname()} Total={trade.pnl:.2f}, No commission={trade.pnlcomm:.2f}')

    def log(self, txt, dt=None):
        """Print string with date to the console"""
        dt = bt.num2date(self.datas[0].datetime[0]) if not dt else dt  # date or date of the current bar
        print(f'{dt.strftime("%d.%m.%Y %H:%M")}, {txt}')  # Print the date and time with the specified text to the console

    def get_position_info(self, exchange, ticker):
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                positions = exchange.fapiPrivateV2GetPositionRisk()
                return next((pos for pos in positions if pos['symbol'] == ticker.replace('/', '')), None)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                print(f"Error getting position info (attempt {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(retry_delay)


if __name__ == '__main__':
    cerebro = bt.Cerebro(quicknotify=True)

    coin_target = 'USDT'  # the base ticker in which calculations will be performed
    symbol = 'ETH' + coin_target  # the ticker by which we will receive data in the format <CodeTickerBaseTicker>

    # Initialize store with futures settings
    store = BinanceStore(
        api_key=Config.BINANCE_API_KEY,
        api_secret=Config.BINANCE_API_SECRET,
        coin_target=coin_target,
        testnet=False
    )

    broker = store.getbroker()
    cerebro.setbroker(broker)

    # Use shorter timeframe for futures trading
    from_date = dt.datetime.utcnow() - dt.timedelta(minutes=5)
    data = store.getdata(
        timeframe=bt.TimeFrame.Minutes,
        compression=1,
        dataname=symbol,
        start_date=from_date,
        LiveBars=True
    )

    cerebro.adddata(data)  # Adding data

    cerebro.addstrategy(JustBuySellStrategy, coin_target=coin_target)  # Adding a trading system

    cerebro.run()  # Launching a trading system
    cerebro.plot()  # Draw a chart
