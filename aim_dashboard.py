import streamlit as st
import pandas as pd
import plotly.express as px

# ページ設定
st.set_page_config(layout="wide")
st.title("RS660 Telemetry Dashboard")

# CSV読み込み関数
@st.cache_data
def load_data(file):
    df = pd.read_csv(file)
    return df

# サイドバーでファイルアップロード
uploaded_file = st.sidebar.file_uploader("CSVファイルを選択", type="csv")

if uploaded_file:
    df = load_data(uploaded_file)
    
    # 概要表示
    st.subheader("Session Overview")
    col1, col2, col3 = st.columns(3)
    col1.metric("Max Speed", f"{df['GPS Speed'].max():.1f} km/h")
    col2.metric("Max Lean", f"{df['Lean Angle'].max():.1f} deg")
    col3.metric("Max RPM", f"{df['RPM dup 2'].max():.0f}")

    # メイングラフ：速度とスロットル
    st.subheader("Time vs Performance")
    fig = px.line(df, x="Time", y=["GPS Speed", "Throttle"], 
                  secondary_y=True, title="Speed & Throttle Correlation")
    st.plotly_chart(fig, use_container_width=True)

    # ギヤ別分布
    st.subheader("Gear Usage")
    fig_gear = px.histogram(df, x="Gear", title="Distribution of Gear Usage")
    st.plotly_chart(fig_gear, use_container_width=True)
    
    # 生データ表示
    with st.expander("Raw Data"):
        st.dataframe(df)

else:
    st.info("CSVファイルをアップロードしてください。")
