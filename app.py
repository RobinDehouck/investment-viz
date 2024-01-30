import base64
import json
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime as dt
import logging
from dash.exceptions import PreventUpdate

# Initialize the Dash app
app = dash.Dash(__name__)

# Define the layout of the app
app.layout = html.Div([
    html.H1("Portfolio Tracker"),
    dcc.Input(id='ticker-input', type='text',
              placeholder='Enter Ticker Symbol'),
    dcc.Input(id='amount-input', type='number',
              placeholder='Enter Amount in USD'),
    dcc.DatePickerSingle(id='purchase-date-input',
                         placeholder='Select Purchase Date', date=dt.today()),
    html.Button('Add Investment', id='submit-val', n_clicks=0),
    # Local storage for investments
    dcc.Store(id='investment-storage', storage_type='local'),
    html.Div(id='investment-list'),
    dcc.Graph(id='global-pnl-chart'),  # Global PnL Chart
    # Container for individual ticker PnL charts
    html.Div(id='individual-charts-container'),
    html.Div(id='close-position-container'),  # Container for closing positions
    # add a text area to log the operations
    html.Button('Reset Investments', id='reset-button', n_clicks=0),
    html.Button('Export Investments', id='export-button', n_clicks=0),
    dcc.Upload(
        id='import-button',
        children=html.Button('Import Investments'),
        multiple=False  # Allow one file at a time
    ),
    html.Div(id='import-output'),  # Placeholder for confirming import action
    dcc.Download(id='download-investment-data'),
    dcc.ConfirmDialog(
    id='confirm-reset',
    message='Are you sure you want to reset all investments?',
),
])

@app.callback(
    Output('confirm-reset', 'displayed'),
    Input('reset-button', 'n_clicks'),
    prevent_initial_call=True
)
def display_confirm(n_clicks):
    return True

@app.callback(
    Output('investment-storage', 'data', allow_duplicate=True),
    Input('import-button', 'contents'),
    State('import-button', 'filename'),
    prevent_initial_call=True
)
def import_investments(contents, filename):
    if contents is None:
        raise PreventUpdate

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    if 'json' in filename:
        data = json.loads(decoded.decode('utf-8'))
        return data
    else:
        return dash.no_update


@app.callback(
    Output('download-investment-data', 'data', allow_duplicate=True),
    Input('export-button', 'n_clicks'),
    State('investment-storage', 'data'),
    prevent_initial_call=True
)
def export_investments(n_clicks, data):
    if data is None:
        data = []
    return dict(content=json.dumps(data, indent=2), filename='investment_data.json')


@app.callback(
    Output('investment-storage', 'data', allow_duplicate=True),
    Input('confirm-reset', 'submit_n_clicks'),
    prevent_initial_call=True
)
def reset_investments(submit_n_clicks):
    if submit_n_clicks:
        return []  # Clear the investment storage if the user confirms

@app.callback(
    Output('investment-storage', 'data', allow_duplicate=True),
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
    new_investment = {'ticker': ticker, 'amount': amount,
                      'purchase_date': purchase_date, 'closures': []}
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
            html.P(
                f"{investment['ticker']} (Amount Open: {investment['amount'] - sum(closure['amount'] for closure in investment['closures'])} USD)"),
            dcc.Input(id={'type': 'close-amount-input', 'index': i},
                      type='number', placeholder='Enter Amount to Close'),
            dcc.DatePickerSingle(id={'type': 'close-date-input', 'index': i},
                                 placeholder='Select Closing Date', date=dt.today()),
            html.Button('Close Position', id={
                        'type': 'close-position-button', 'index': i}, n_clicks=0),
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
            open_amount = storage_data[index]['amount'] - sum(
                closure['amount'] for closure in storage_data[index]['closures'])
            if close_amounts[index] > open_amount:
                confirm_messages[
                    index] = f"Error: Attempt to close more than available amount. Available: {open_amount} USD"
            else:
                closure_date = close_dates[index]
                storage_data[index]['closures'].append(
                    {'amount': close_amounts[index], 'date': closure_date.isoformat()})
                confirm_messages[
                    index] = f"Successfully closed {close_amounts[index]} USD on {closure_date.strftime('%Y-%m-%d')}"
        except Exception as e:
            logging.error(f"Error closing position: {e}")
            confirm_messages[index] = f"Error closing position: {e}"

    return confirm_messages, storage_data

# Callback to update charts based on stored data


@app.callback(
    [Output('global-pnl-chart', 'figure'),
     Output('individual-charts-container', 'children')],
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
        purchase_date = pd.Timestamp(investment['purchase_date'])

        tickerData = yf.Ticker(ticker)
        df = tickerData.history(period='1d', start=purchase_date.strftime(
            '%Y-%m-%d'), end=pd.Timestamp('now').strftime('%Y-%m-%d'))

        if df.empty:
            continue

        df.index = df.index.tz_localize(None)
        df['PnL'] = 0
        original_purchase_price = df['Close'].iloc[0]

        for closure in investment['closures']:
            closure_date = pd.Timestamp(closure['date'])
            closure_amount = closure['amount']

            if closure_date in df.index:
                closure_price = df.loc[closure_date]['Close']
            else:
                closure_price = df[df.index >
                                   closure_date].iloc[0]['Close'] if not df[df.index > closure_date].empty else 0

            if closure_price > 0:
                num_shares_closed = closure_amount / closure_price
                # Calculate the PnL adjustment for the closed shares until the closure date
                pnl_adjustment = (
                    closure_price - original_purchase_price) * num_shares_closed
                # Adjust the PnL for dates after the closure
                df.loc[closure_date:, 'PnL'] += pnl_adjustment
                # Adjust the total amount for the remaining open shares
                amount -= closure_amount

        # Calculate the PnL for remaining open shares
        if amount > 0:
            num_shares_remaining = amount / original_purchase_price
            df.loc[:, 'PnL'] += (df['Close'] -
                                 original_purchase_price) * num_shares_remaining

        chart_data = go.Figure()
        chart_data.add_trace(go.Scatter(
            x=df.index, y=df['PnL'], mode='lines+markers', name=f'{ticker} PnL'))
        chart_data.update_layout(title=f'PnL for {ticker}',
                                 xaxis_title='Date',
                                 yaxis_title='Profit and Loss (USD)')
        individual_charts.append(dcc.Graph(figure=chart_data))

        if global_pnl_data.empty:
            global_pnl_data = df[['PnL']].copy()
        else:
            global_pnl_data = global_pnl_data.join(
                df[['PnL']], how='outer', rsuffix=f'_{ticker}')
            global_pnl_data.fillna(method='ffill', inplace=True)
            global_pnl_data.fillna(0, inplace=True)

    global_pnl_data['Total PnL'] = global_pnl_data.sum(axis=1)

    global_chart_data = go.Figure()
    global_chart_data.add_trace(go.Scatter(
        x=global_pnl_data.index, y=global_pnl_data['Total PnL'], mode='lines+markers', name='Total PnL'))
    global_chart_data.update_layout(title='Global Portfolio PnL',
                                    xaxis_title='Date',
                                    yaxis_title='Total Profit and Loss (USD)')

    return global_chart_data, individual_charts


# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
