import copy
import time
import warnings

warnings.filterwarnings("ignore")
from typing import List

import pandas as pd
from tqdm import tqdm
from matplotlib import pyplot as plt

import stockstats
import talib
from meta.data_processors._base import _Base

import tushare as ts


class Tushare(_Base):
    """
    key-value in kwargs
    ----------
        token : str
            get from https://waditu.com/ after registration
        adj: str
            Whether to use adjusted closing price. Default is None.
            If you want to use forward adjusted closing price or 前复权. pleses use 'qfq'
            If you want to use backward adjusted closing price or 后复权. pleses use 'hfq'
    """

    def __init__(
        self,
        data_source: str,
        start_date: str,
        end_date: str,
        time_interval: str,
        **kwargs,
    ):
        super().__init__(data_source, start_date, end_date, time_interval, **kwargs)
        assert "token" in kwargs.keys(), "Please input token!"
        self.token = kwargs["token"]
        if "adj" in kwargs.keys():
            self.adj = kwargs["adj"]
            print(f"Using {self.adj} method.")
        else:
            self.adj = None

    def get_data(self, id) -> pd.DataFrame:
        # df1 = ts.pro_bar(ts_code=id, start_date=self.start_date,end_date='20180101')
        # dfb=pd.concat([df, df1], ignore_index=True)
        # print(dfb.shape)
        return ts.pro_bar(
            ts_code=id,
            start_date=self.start_date,
            end_date=self.end_date,
            adj=self.adj,
        )

    def download_data(self, ticker_list: List[str]):
        """
        `pd.DataFrame`
            7 columns: A tick symbol, date, open, high, low, close and volume
            for the specified stock ticker
        """
        assert self.time_interval == "1d", "Not supported currently"

        self.ticker_list = ticker_list
        ts.set_token(self.token)

        self.dataframe = pd.DataFrame()
        for i in tqdm(ticker_list, total=len(ticker_list)):
            # nonstandard_id = self.transfer_standard_ticker_to_nonstandard(i)
            # df_temp = self.get_data(nonstandard_id)
            df_temp = self.get_data(i)
            self.dataframe = self.dataframe.append(df_temp)
            # print("{} ok".format(i))
            time.sleep(0.25)

        self.dataframe.columns = [
            "tic",
            "date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "volume",
            "amount",
        ]
        self.dataframe.sort_values(by=["date", "tic"], inplace=True)
        self.dataframe.reset_index(drop=True, inplace=True)

        self.dataframe = self.dataframe[
            ["tic", "date", "open", "high", "low", "close", "volume"]
        ]
        # self.dataframe.loc[:, 'tic'] = pd.DataFrame((self.dataframe['tic'].tolist()))
        self.dataframe["date"] = pd.to_datetime(self.dataframe["date"], format="%Y%m%d")
        self.dataframe["day"] = self.dataframe["date"].dt.dayofweek
        self.dataframe["date"] = self.dataframe.date.apply(
            lambda x: x.strftime("%Y-%m-%d")
        )

        self.dataframe.dropna(inplace=True)
        self.dataframe.sort_values(by=["date", "tic"], inplace=True)
        self.dataframe.reset_index(drop=True, inplace=True)

        print("Shape of DataFrame: ", self.dataframe.shape)

    def clean_data(self):
        dfc = copy.deepcopy(self.dataframe)

        dfcode = pd.DataFrame(columns=["tic"])
        dfdate = pd.DataFrame(columns=["date"])

        dfcode.tic = dfc.tic.unique()

        if "time" in dfc.columns.values.tolist():
            dfc = dfc.rename(columns={"time": "date"})

        dfdate.date = dfc.date.unique()
        dfdate.sort_values(by="date", ascending=False, ignore_index=True, inplace=True)

        # the old pandas may not support pd.merge(how="cross")
        try:
            df1 = pd.merge(dfcode, dfdate, how="cross")
        except:
            print("Please wait for a few seconds...")
            df1 = pd.DataFrame(columns=["tic", "date"])
            for i in range(dfcode.shape[0]):
                for j in range(dfdate.shape[0]):
                    df1 = df1.append(
                        pd.DataFrame(
                            data={
                                "tic": dfcode.iat[i, 0],
                                "date": dfdate.iat[j, 0],
                            },
                            index=[(i + 1) * (j + 1) - 1],
                        )
                    )

        df2 = pd.merge(df1, dfc, how="left", on=["tic", "date"])

        # back fill missing data then front fill
        df3 = pd.DataFrame(columns=df2.columns)
        for i in self.ticker_list:
            df4 = df2[df2.tic == i].fillna(method="bfill").fillna(method="ffill")
            df3 = pd.concat([df3, df4], ignore_index=True)

        df3 = df3.fillna(0)

        # reshape dataframe
        df3 = df3.sort_values(by=["date", "tic"]).reset_index(drop=True)

        print("Shape of DataFrame: ", df3.shape)

        self.dataframe = df3

    def add_technical_indicator(
        self,
        tech_indicator_list: List[str],
        select_stockstats_talib: int = 0,
        drop_na_timestpe: int = 0,
    ):
        """
        calculate technical indicators
        use stockstats/talib package to add technical inidactors
        :param data: (df) pandas dataframe
        :return: (df) pandas dataframe
        """
        if "date" in self.dataframe.columns.values.tolist():
            self.dataframe.rename(columns={"date": "time"}, inplace=True)

        if self.data_source == "ccxt":
            self.dataframe.rename(columns={"index": "time"}, inplace=True)

        self.dataframe.reset_index(drop=False, inplace=True)
        if "level_1" in self.dataframe.columns:
            self.dataframe.drop(columns=["level_1"], inplace=True)
        if "level_0" in self.dataframe.columns and "tic" not in self.dataframe.columns:
            self.dataframe.rename(columns={"level_0": "tic"}, inplace=True)
        assert select_stockstats_talib in {0, 1}
        print("tech_indicator_list: ", tech_indicator_list)
        if select_stockstats_talib == 0:  # use stockstats
            stock = stockstats.StockDataFrame.retype(self.dataframe)
            unique_ticker = stock.tic.unique()
            for indicator in tech_indicator_list:
                print("indicator: ", indicator)
                indicator_df = pd.DataFrame()
                for i in range(len(unique_ticker)):
                    try:
                        temp_indicator = stock[stock.tic == unique_ticker[i]][indicator]
                        temp_indicator = pd.DataFrame(temp_indicator)
                        temp_indicator["tic"] = unique_ticker[i]
                        temp_indicator["time"] = self.dataframe[
                            self.dataframe.tic == unique_ticker[i]
                        ]["time"].to_list()
                        indicator_df = pd.concat(
                            [indicator_df, temp_indicator],
                            axis=0,
                            join="outer",
                            ignore_index=True,
                        )
                    except Exception as e:
                        print(e)
                if not indicator_df.empty:
                    self.dataframe = self.dataframe.merge(
                        indicator_df[["tic", "time", indicator]],
                        on=["tic", "time"],
                        how="left",
                    )
        else:  # use talib
            final_df = pd.DataFrame()
            for i in self.dataframe.tic.unique():
                tic_df = self.dataframe[self.dataframe.tic == i]
                (
                    tic_df.loc["macd"],
                    tic_df.loc["macd_signal"],
                    tic_df.loc["macd_hist"],
                ) = talib.MACD(
                    tic_df["close"],
                    fastperiod=12,
                    slowperiod=26,
                    signalperiod=9,
                )
                tic_df.loc["rsi"] = talib.RSI(tic_df["close"], timeperiod=14)
                tic_df.loc["cci"] = talib.CCI(
                    tic_df["high"],
                    tic_df["low"],
                    tic_df["close"],
                    timeperiod=14,
                )
                tic_df.loc["dx"] = talib.DX(
                    tic_df["high"],
                    tic_df["low"],
                    tic_df["close"],
                    timeperiod=14,
                )
                final_df = pd.concat([final_df, tic_df], axis=0, join="outer")
            self.dataframe = final_df

        self.dataframe.sort_values(by=["time", "tic"], inplace=True)
        if drop_na_timestpe:
            time_to_drop = self.dataframe[
                self.dataframe.isna().any(axis=1)
            ].time.unique()
            self.dataframe = self.dataframe[~self.dataframe.time.isin(time_to_drop)]
        self.dataframe.rename(columns={"time": "date"}, inplace=True)
        print("Succesfully add technical indicators")

    # def get_trading_days(self, start: str, end: str) -> List[str]:
    #     print('not supported currently!')
    #     return ['not supported currently!']

    # def add_turbulence(self, data: pd.DataFrame) \
    #         -> pd.DataFrame:
    #     print('not supported currently!')
    #     return pd.DataFrame(['not supported currently!'])

    # def calculate_turbulence(self, data: pd.DataFrame, time_period: int = 252) \
    #         -> pd.DataFrame:
    #     print('not supported currently!')
    #     return pd.DataFrame(['not supported currently!'])

    # def add_vix(self, data: pd.DataFrame) \
    #         -> pd.DataFrame:
    #     print('not supported currently!')
    #     return pd.DataFrame(['not supported currently!'])

    # def df_to_array(self, df: pd.DataFrame, tech_indicator_list: List[str], if_vix: bool) \
    #         -> List[np.array]:
    #     print('not supported currently!')
    #     return pd.DataFrame(['not supported currently!'])

    def data_split(self, df, start, end, target_date_col="date"):
        """
        split the dataset into training or testing using date
        :param data: (df) pandas dataframe, start, end
        :return: (df) pandas dataframe
        """
        data = df[(df[target_date_col] >= start) & (df[target_date_col] < end)]
        data = data.sort_values([target_date_col, "tic"], ignore_index=True)
        data.index = data[target_date_col].factorize()[0]
        return data

    # "600000.XSHG" -> "600000.SH"
    # "000612.XSHE" -> "000612.SZ"
    def transfer_standard_ticker_to_nonstandard(self, ticker: str) -> str:
        n, alpha = ticker.split(".")
        assert alpha in ["XSHG", "XSHE"], "Wrong alpha"
        if alpha == "XSHG":
            nonstandard_ticker = n + ".SH"
        elif alpha == "XSHE":
            nonstandard_ticker = n + ".SZ"
        return nonstandard_ticker


class ReturnPlotter:
    """
    An easy-to-use plotting tool to plot cumulative returns over time.
    Baseline supports equal weighting(default) and any stocks you want to use for comparison.
    """

    def __init__(self, df_account_value, df_trade, start_date, end_date):
        self.start = start_date
        self.end = end_date
        self.trade = df_trade
        self.df_account_value = df_account_value

    def get_baseline(self, ticket):
        df = ts.get_hist_data(ticket, start=self.start, end=self.end)
        df.loc[:, "dt"] = df.index
        df.index = range(len(df))
        df.sort_values(axis=0, by="dt", ascending=True, inplace=True)
        df["date"] = pd.to_datetime(df["dt"], format="%Y-%m-%d")
        return df

    def plot(self, baseline_ticket=None):
        """
        Plot cumulative returns over time.
        use baseline_ticket to specify stock you want to use for comparison
        (default: equal weighted returns)
        """
        baseline_label = "Equal-weight portfolio"
        tic2label = {"399300": "CSI 300 Index", "000016": "SSE 50 Index"}
        if baseline_ticket:
            # 使用指定ticket作为baseline
            baseline_df = self.get_baseline(baseline_ticket)
            baseline_date_list = baseline_df.date.dt.strftime("%Y-%m-%d").tolist()
            df_date_list = self.df_account_value.date.tolist()
            df_account_value = self.df_account_value[
                self.df_account_value.date.isin(baseline_date_list)
            ]
            baseline_df = baseline_df[baseline_df.date.isin(df_date_list)]
            baseline = baseline_df.close.tolist()
            baseline_label = tic2label.get(baseline_ticket, baseline_ticket)
            ours = df_account_value.account_value.tolist()
        else:
            # 均等权重
            all_date = self.trade.date.unique().tolist()
            baseline = []
            for day in all_date:
                day_close = self.trade[self.trade["date"] == day].close.tolist()
                avg_close = sum(day_close) / len(day_close)
                baseline.append(avg_close)
            ours = self.df_account_value.account_value.tolist()

        ours = self.pct(ours)
        baseline = self.pct(baseline)

        days_per_tick = (
            60  # you should scale this variable accroding to the total trading days
        )
        time = list(range(len(ours)))
        datetimes = self.df_account_value.date.tolist()
        ticks = [tick for t, tick in zip(time, datetimes) if t % days_per_tick == 0]
        plt.title("Cumulative Returns")
        plt.plot(time, ours, label="DDPG Agent", color="green")
        plt.plot(time, baseline, label=baseline_label, color="grey")
        plt.xticks([i * days_per_tick for i in range(len(ticks))], ticks, fontsize=7)

        plt.xlabel("Date")
        plt.ylabel("Cumulative Return")

        plt.legend()
        plt.show()
        plt.savefig(f"plot_{baseline_ticket}.png")

    def plot_all(self):
        baseline_label = "Equal-weight portfolio"
        tic2label = {"399300": "CSI 300 Index", "000016": "SSE 50 Index"}

        # date lists
        # algorithm date list
        df_date_list = self.df_account_value.date.tolist()

        # 399300 date list
        csi300_df = self.get_baseline("399300")
        csi300_date_list = csi300_df.date.dt.strftime("%Y-%m-%d").tolist()

        # 000016 date list
        sh50_df = self.get_baseline("000016")
        sh50_date_list = sh50_df.date.dt.strftime("%Y-%m-%d").tolist()

        # find intersection
        all_date = sorted(
            list(set(df_date_list) & set(csi300_date_list) & set(sh50_date_list))
        )

        # filter data
        csi300_df = csi300_df[csi300_df.date.isin(all_date)]
        baseline_300 = csi300_df.close.tolist()
        baseline_label_300 = tic2label["399300"]

        sh50_df = sh50_df[sh50_df.date.isin(all_date)]
        baseline_50 = sh50_df.close.tolist()
        baseline_label_50 = tic2label["000016"]

        # 均等权重
        baseline_equal_weight = []
        for day in all_date:
            day_close = self.trade[self.trade["date"] == day].close.tolist()
            avg_close = sum(day_close) / len(day_close)
            baseline_equal_weight.append(avg_close)

        df_account_value = self.df_account_value[
            self.df_account_value.date.isin(all_date)
        ]
        ours = df_account_value.account_value.tolist()

        ours = self.pct(ours)
        baseline_300 = self.pct(baseline_300)
        baseline_50 = self.pct(baseline_50)
        baseline_equal_weight = self.pct(baseline_equal_weight)

        days_per_tick = (
            60  # you should scale this variable accroding to the total trading days
        )
        time = list(range(len(ours)))
        datetimes = self.df_account_value.date.tolist()
        ticks = [tick for t, tick in zip(time, datetimes) if t % days_per_tick == 0]
        plt.title("Cumulative Returns")
        plt.plot(time, ours, label="DDPG Agent", color="darkorange")
        plt.plot(
            time,
            baseline_equal_weight,
            label=baseline_label,
            color="cornflowerblue",
        )  # equal weight
        plt.plot(
            time, baseline_300, label=baseline_label_300, color="lightgreen"
        )  # 399300
        plt.plot(time, baseline_50, label=baseline_label_50, color="silver")  # 000016
        plt.xlabel("Date")
        plt.ylabel("Cumulative Return")

        plt.xticks([i * days_per_tick for i in range(len(ticks))], ticks, fontsize=7)
        plt.legend()
        plt.show()
        plt.savefig("./plot_all.png")

    def pct(self, l):
        """Get percentage"""
        base = l[0]
        return [x / base for x in l]

    def get_return(self, df, value_col_name="account_value"):
        df = copy.deepcopy(df)
        df["daily_return"] = df[value_col_name].pct_change(1)
        df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
        df.set_index("date", inplace=True, drop=True)
        df.index = df.index.tz_localize("UTC")
        return pd.Series(df["daily_return"], index=df.index)
