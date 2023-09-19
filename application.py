from flask import Flask,render_template
import time,ta
import pandas as pd
import numpy as np
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf
import pytz

# it will get the time zone 
# of the specified location
IST = pytz.timezone('Asia/Kolkata')

scheduler = BackgroundScheduler()
def alltimehigh(close):
    return int(max(close)==close.iloc[-1])

def Supertrend(df, atr_period, multiplier):
    
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # calculate ATR
    price_diffs = [high - low, 
                   high - close.shift(), 
                   close.shift() - low]
    true_range = pd.concat(price_diffs, axis=1)
    true_range = true_range.abs().max(axis=1)
    # default ATR calculation in supertrend indicator
    atr = true_range.ewm(alpha=1/atr_period,min_periods=atr_period).mean() 
    # df['atr'] = df['tr'].rolling(atr_period).mean()
    
    # HL2 is simply the average of high and low prices
    hl2 = (high + low) / 2
    # upperband and lowerband calculation
    # notice that final bands are set to be equal to the respective bands
    final_upperband = upperband = hl2 + (multiplier * atr)
    final_lowerband = lowerband = hl2 - (multiplier * atr)
    
    # initialize Supertrend column to True
    supertrend = [True] * len(df)
    
    for i in range(1, len(df.index)):
        curr, prev = i, i-1
        
        # if current close price crosses above upperband
        if close[curr] > final_upperband[prev]:
            supertrend[curr] = True
        # if current close price crosses below lowerband
        elif close[curr] < final_lowerband[prev]:
            supertrend[curr] = False
        # else, the trend continues
        else:
            supertrend[curr] = supertrend[prev]
            
            # adjustment to the final bands
            if supertrend[curr] == True and final_lowerband[curr] < final_lowerband[prev]:
                final_lowerband[curr] = final_lowerband[prev]
            if supertrend[curr] == False and final_upperband[curr] > final_upperband[prev]:
                final_upperband[curr] = final_upperband[prev]

        # to remove bands according to the trend direction
        if supertrend[curr] == True:
            final_upperband[curr] = np.nan
        else:
            final_lowerband[curr] = np.nan

    return pd.Series(final_lowerband)    

def stock_process(company, start, end,interval="1d"):
    try:

        df = yf.download(tickers=company['Symbol'], interval=interval, start=start,end=end) 
    
        df['All time high']=df['Close'].apply(lambda x:alltimehigh(df['Close']))

        df['MACD hist']=ta.trend.macd_diff(df['Close'])
        df['MACD hist sloap*']=df['MACD hist'].diff()

        df["ema 50"] = ta.trend.EMAIndicator(df['Close'], window=50, fillna=False).ema_indicator()
        df["ema 100"] = ta.trend.EMAIndicator(df['Close'], window=100, fillna=False).ema_indicator()
        # df["ema 200"] = ta.trend.EMAIndicator(df['Close'], window=200, fillna=False).ema_indicator()

        df["ema 50 Sloap"]=(df["ema 50"].diff()/df['Close'])*100
        df["ema 100 Sloap"]=(df['ema 100'].diff()/df['Close'])*100
        # df["ema 200 Sloap"]=df['ema 200'].diff()/df['Close']

        df['Super Trend']=Supertrend(df,10,2)
        df['target']=1.8*(((df['Open']+df['Close'])/2)-df['Super Trend'])+df['Close']
        
        last = pd.Series(df.iloc[-1])
        last["Company"] = (company.loc['Company Name'])
        last.rename({"Close": "*Price"}, inplace=True)
        last.drop(["Open", "High", "Low","Volume"], inplace=True)

        last["ema 50 2nd diff"]=(df.iloc[-1]["ema 50 Sloap"]-df.iloc[-2]["ema 50 Sloap"])*100
        last["ema 100 2nd diff"]=(df.iloc[-1]["ema 100 Sloap"]-df.iloc[-2]["ema 100 Sloap"])*100
        # last["ema 200 2nd diff"]=df.iloc[-1]["ema 200 Sloap"]-df.iloc[-2]["ema 200 Sloap"]
        last['signal']=df.iloc[-1]['Close']>df.iloc[-1]['Open']

        #print(last)

        return last

    except Exception as e:
        print(e)

def preprocess(df):
    new_df=df[(df['signal']==True) & (df['ema 50 2nd diff']>0) & (df['MACD hist sloap*']>0) & (df['Super Trend']!=None) & (df['ema 50 Sloap']>0)]
    new_df=new_df.sort_values("ema 50 Sloap",ascending=0)
    return new_df

def scheduled_job():
    final_data=[]
    # interval="ONE_DAY"#FIFTEEN_MINUTE,FIVE_MINUTE
    from_Date="2000-08-01"
    to_Date=None
    
    data=pd.read_excel("stock_data_nifty200.xlsx",index_col='index')

    for i in range(len(data)):
        final_data.append(stock_process(data.iloc[i],  from_Date, to_Date))
  
    result = pd.concat(final_data, axis=1).T.set_index("Company")
    result.sort_index(axis=1, inplace=True)
    print(result)

    f=open("time.txt","w")
    f.write(str(datetime.now(IST)))
    f.close()

    result.to_excel("data.xlsx")

# Schedule the job to run every set interval
scheduler.add_job(scheduled_job, 'interval', seconds=900)
scheduler.start()

application = Flask(__name__)
application.static_folder = 'static'

@application.route("/")
def hello_world():
    return render_template("index.html")

@application.route("/result",methods=["POST","GET"])
def hello_world1():
    scheduled_job()
    result=pd.read_excel("data.xlsx")
    process_data=preprocess(result)
    return render_template("result.html",Result=result.to_html(table_id='full_data_table', escape=False),Pdata=process_data.to_html(table_id='preocced_data', escape=False,))

@application.route("/view",methods=["POST","GET"])
def view():
    result=pd.read_excel("data.xlsx")
    process_data=preprocess(result)
    file=open("time.txt","r")
    r=file.read()
    file.close()
    return render_template("view.html",Result=result.to_html(table_id='full_data_table', escape=False),Pdata=process_data.to_html(table_id='preocced_data', escape=False,),Time=r)

if __name__=="__main__":
    application.run(host="0.0.0.0")

            
