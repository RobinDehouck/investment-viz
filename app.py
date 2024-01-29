import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime as dt
import logging

# Initialize the Dash app
app = dash.Dash(__name__)

# Define the layout of the app
app.layout = html.Div([
    html.H1("Portfolio Tracker"),
    dcc.Input(id='ticker-input', type='text', placeholder='Enter Ticker Symbol'),
    dcc.Input(id='amount-input', type='number', placeholder='Enter Amount in USD'),
    dcc.DatePickerSingle(id='purchase-date-input', placeholder='Select Purchase Date', date=dt.today()),
    html.Button('Add Investment', id='submit-val', n_clicks=0),
    dcc.Store(id='investment-storage', storage_type='local'),  # Local storage for investments
    html.Div(id='investment-list'),
    dcc.Graph(id='global-pnl-chart'),  # Global PnL Chart
    html.Div(id='individual-charts-container'),  # Container for individual ticker PnL charts
    html.Div(id='close-position-container'),  # Container for closing positions
    # add a text area to log the operations
    html.Div(id='log-area')
])

# Callback to add investment to local storage
@app.callback(
    Output('investment-storage', 'data'),
    Input('submit-val', 'n_clicks'),
    [State('investment-storage', 'data'),
     State('ticker-input', 'value'),
     State('amount-input', 'value'),
     State('purchase-date-input', 'date')],
    prevent_initial_call=True
)
def store_investment_data(n_clicks, storage_data, ticker, amount, purchase_date):
    if storage_data is None:
        storage_data = []
    new_investment = {'ticker': ticker, 'amount': amount, 'purchase_date': purchase_date, 'closures': []}
    storage_data.append(new_investment)
    return storage_data

# Callback to generate close position inputs dynamically based on stored investments
@app.callback(
    Output('close-position-container', 'children'),
    Input('investment-storage', 'data')
)
def generate_close_position_inputs(storage_data):
    if storage_data is None:
        return []

    close_position_elements = []
    for i, investment in enumerate(storage_data):
        close_position_elements.append(html.Div([
            html.P(f"{investment['ticker']} (Amount Open: {investment['amount'] - sum(closure['amount'] for closure in investment['closures'])} USD)"),
            dcc.Input(id={'type': 'close-amount-input', 'index': i}, type='number', placeholder='Enter Amount to Close'),
            dcc.DatePickerSingle(id={'type': 'close-date-input', 'index': i}, placeholder='Select Closing Date', date=dt.today()),
            html.Button('Close Position', id={'type': 'close-position-button', 'index': i}, n_clicks=0),
            html.Div(id={'type': 'close-confirm', 'index': i}, children='')
        ]))

    return close_position_elements

# Callback to close a portion of an investment
@app.callback(
    [Output({'type': 'close-confirm', 'index': dash.ALL}, 'children'),
     Output('investment-storage', 'data', allow_duplicate=True)],
    Input({'type': 'close-position-button', 'index': dash.ALL}, 'n_clicks'),
    [State('investment-storage', 'data'),
     State({'type': 'close-amount-input', 'index': dash.ALL}, 'value'),
     State({'type': 'close-date-input', 'index': dash.ALL}, 'date')],
    prevent_initial_call=True
)
def close_investment_position(n_clicks, storage_data, close_amounts, close_dates):
    ctx = dash.callback_context
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    button_id = eval(triggered) if triggered else {'index': None}
    index = button_id.get('index')

    # Ensure close_dates are parsed correctly as pd.Timestamp objects
    close_dates = [pd.Timestamp(date) for date in close_dates]

    confirm_messages = [''] * len(storage_data)

    if index is not None and close_amounts[index] is not None and close_dates[index] is not None:
        try:
            open_amount = storage_data[index]['amount'] - sum(closure['amount'] for closure in storage_data[index]['closures'])
            if close_amounts[index] > open_amount:
                confirm_messages[index] = f"Error: Attempt to close more than available amount. Available: {open_amount} USD"
            else:
                closure_date = close_dates[index]
                storage_data[index]['closures'].append({'amount': close_amounts[index], 'date': closure_date.isoformat()})
                confirm_messages[index] = f"Successfully closed {close_amounts[index]} USD on {closure_date.strftime('%Y-%m-%d')}"
        except Exception as e:
            logging.error(f"Error closing position: {e}")
            confirm_messages[index] = f"Error closing position: {e}"

    return confirm_messages, storage_data

# Callback to update charts based on stored data
@app.callback(
    [Output('global-pnl-chart', 'figure'), Output('individual-charts-container', 'children')],
    Input('investment-storage', 'data')
)
def update_charts(storage_data):
    if storage_data is None:
        return go.Figure(), []

    global_pnl_data = pd.DataFrame()
    individual_charts = []

    for investment in storage_data:
        ticker = investment['ticker']
        amount = float(investment['amount'])
        # Convert purchase_date to pd.Timestamp
        purchase_date = pd.Timestamp(investment['purchase_date'])

        tickerData = yf.Ticker(ticker)
        # Ensure the start date is formatted correctly
        df = tickerData.history(period='1d', start=purchase_date.strftime('%Y-%m-%d'), end=pd.Timestamp('now').strftime('%Y-%m-%d'))

        # Ensure DataFrame operations use compatible date types
        if df.empty:
            continue

        df.index = df.index.tz_localize(None)
        df['PnL'] = 0

        for closure in investment['closures']:
            # Convert closure date to pd.Timestamp
            closure_date = pd.Timestamp(closure['date'])
            closure_amount = closure['amount']
            
            # Ensure comparisons use compatible date types
            if closure_date in df.index:
                closure_price = df.loc[closure_date]['Close']
            else:
                closure_price = df[df.index > closure_date].iloc[0]['Close'] if not df[df.index > closure_date].empty else 0

            if closure_price > 0:
                amount -= closure_amount
                num_shares_closed = closure_amount / closure_price
                df.loc[:closure_date, 'PnL'] += (df['Close'] - df['Close'].iloc[0]) * num_shares_closed

        # Continue tracking the remaining open position
        if amount > 0:  # Check if there is any remaining amount to avoid division by zero
            num_shares_remaining = amount / df['Close'].iloc[0]
            df['PnL'] += (df['Close'] - df['Close'].iloc[0]) * num_shares_remaining

        # Generate the individual chart for the current ticker
        chart_data = go.Figure()
        chart_data.add_trace(go.Scatter(x=df.index, y=df['PnL'], mode='lines+markers', name=f'{ticker} PnL'))
        chart_data.update_layout(title=f'PnL for {ticker}',
                                 xaxis_title='Date',
                                 yaxis_title='Profit and Loss (USD)')
        individual_charts.append(dcc.Graph(figure=chart_data))

        # Append PnL to the global DataFrame
        if global_pnl_data.empty:
            global_pnl_data = df[['PnL']].copy()
        else:
            global_pnl_data = global_pnl_data.join(df[['PnL']], how='outer', rsuffix=f'_{ticker}')
            global_pnl_data.fillna(method='ffill', inplace=True)
            global_pnl_data.fillna(0, inplace=True)

    # Calculate the total PnL by summing across columns for each row
    global_pnl_data['Total PnL'] = global_pnl_data.sum(axis=1)

    # Generate the global PnL chart
    global_chart_data = go.Figure()
    global_chart_data.add_trace(go.Scatter(x=global_pnl_data.index, y=global_pnl_data['Total PnL'], mode='lines+markers', name='Total PnL'))
    global_chart_data.update_layout(title='Global Portfolio PnL',
                                    xaxis_title='Date',
                                    yaxis_title='Total Profit and Loss (USD)')

    return global_chart_data, individual_charts

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
