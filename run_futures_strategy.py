import logging
from datetime import datetime, timedelta
from ccxt_store.ccxt_store import CCXTStore
from ccxt_store.ccxt_feed import CCXTFeed
from ccxt_store.ccxt_broker import CCXTBroker
from ccxt_store.strategies.futures_strategy import FuturesStrategy
from ConfigBinance.Config import Config  # Configuration file
import time

def main():
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    # 设置交易对
    symbols = ['ETHUSDT']
    
    # 初始化store
    store = CCXTStore(
        exchange_name='binance',
        api_key=Config.BINANCE_API_KEY,
        secret_key=Config.BINANCE_API_SECRET,
        additional_options={
            'defaultType': 'future',
            'adjustForTimeDifference': True,
            'hedgeMode': False,
        },
        symbols=symbols
    )
    
    # 初始化broker
    broker = CCXTBroker(
        store=store,
        leverage=50,
        margin_mode='isolated',
        default_type='future'
    )
    
    # 初始化策略
    strategy = FuturesStrategy(
        broker=broker,
        symbols=symbols,
        leverage=50,
        min_position_value=100  # 目标仓位价值100 USDT。例如：以50倍杠杆开仓，实际需要保证金为2 USDT (100/50)。再加上10%缓冲，最终需要2.2 USDT保证金
    )
    
    # 初始化数据馈送
    feeds = {}
    for symbol in symbols:
        feed = CCXTFeed(
            store=store,
            symbol=symbol,
            timeframe='1m',
            start_date=datetime.utcnow() - timedelta(minutes=5),
            live=True
        )
        feeds[symbol] = feed
        feed.start()
    
    # 运行策略
    try:
        while True:
            for symbol, feed in feeds.items():
                data = feed._get_new_data()
                if data:
                    strategy.on_data(symbol, data)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Strategy stopped by user")
    except Exception as e:
        print(f"Strategy stopped due to error: {str(e)}")
        
if __name__ == '__main__':
    main()
