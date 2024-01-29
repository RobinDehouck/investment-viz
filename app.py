import dash
import json
from dash import dcc, html
from dash.dependencies import Input, Output, State
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime as dt
from dash.exceptions import PreventUpdate

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Portfolio Tracker"),
    html.Div([
        dcc.Input(id='ticker-input', type='text', placeholder='Enter Ticker Symbol'),
        dcc.Input(id='amount-input', type='number', placeholder='Enter Amount in USD'),
        dcc.DatePickerSingle(id='purchase-date-input', placeholder='Select Purchase Date', date=dt.today()),
        html.Button('Add Investment', id='submit-val', n_clicks=0),
    ]),
    html.Div(id='current-investments'),
    dcc.Store(id='investment-storage', storage_type='local'),
    dcc.Graph(id='global-pnl-chart'),
    html.Div(id='individual-charts-container')
])

@app.callback(
    Output('investment-storage', 'data'),
    [Input('submit-val', 'n_clicks'),
     Input('close-selected-investment', 'n_clicks')],
    [State('investment-storage', 'data'),
     State('ticker-input', 'value'),
     State('amount-input', 'value'),
     State('purchase-date-input', 'date'),
     State('close-ticker-dropdown', 'value'),
     State('sell-amount-input', 'value'),
     State('sell-date-input', 'date')],
    prevent_initial_call=True
)
def manage_investments(add_clicks, close_clicks, storage_data, ticker, amount, purchase_date, selected_index, sell_amount, sell_date):
    ctx = dash.callback_context

    if not ctx.triggered:
        raise PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'submit-val':
        if storage_data is None:
            storage_data = []
        new_investment = {'ticker': ticker, 'amount': amount, 'purchase_date': purchase_date, 'status': 'open'}
        storage_data.append(new_investment)

    elif trigger_id == 'close-selected-investment' and selected_index is not None:
        if 0 <= selected_index < len(storage_data) and storage_data[selected_index]['status'] == 'open':
            storage_data[selected_index]['status'] = 'closed'
            storage_data[selected_index]['sell_amount'] = sell_amount
            storage_data[selected_index]['sell_date'] = sell_date

    return storage_data

@app.callback(
    Output('current-investments', 'children'),
    Input('investment-storage', 'data')
)
def display_current_investments(storage_data):
    if storage_data is None:
        return []
    open_investments = [inv for inv in storage_data if inv['status'] == 'open']
    if not open_investments:
        return [html.P("No open investments to display.")]
    
    children = [
        html.Div([
            dcc.Dropdown(
                id='close-ticker-dropdown',
                options=[{'label': inv['ticker'], 'value': i} for i, inv in enumerate(open_investments)],
                placeholder='Select Ticker to Close'
            ),
            dcc.Input(id='sell-amount-input', type='number', placeholder='Enter Sell Amount in USD'),
            dcc.DatePickerSingle(id='sell-date-input', placeholder='Select Sell Date', date=dt.today()),
            html.Button('Close Selected Investment', id='close-selected-investment', n_clicks=0),
        ], style={'margin-bottom': '20px'})
    ]
    return children

@app.callback(
    Output('investment-storage', 'data'),
    Input('close-selected-investment', 'n_clicks'),
    [State('investment-storage', 'data'),
     State('close-ticker-dropdown', 'value'),
     State('sell-amount-input', 'value'),
     State('sell-date-input', 'date')],
    prevent_initial_call=True
)
def close_investment(n_clicks, storage_data, selected_index, sell_amount, sell_date):
    if selected_index is not None and storage_data[selected_index]['status'] == 'open':
        storage_data[selected_index]['status'] = 'closed'
        storage_data[selected_index]['sell_amount'] = sell_amount
        storage_data[selected_index]['sell_date'] = sell_date
    return storage_data
if __name__ == '__main__':
    app.run_server(debug=True)
