import base64
import json
import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime as dt
from dash.exceptions import PreventUpdate

app = dash.Dash(__name__, external_stylesheets=[
                'https://codepen.io/chriddyp/pen/bWLwgP.css'])

app.layout = html.Div([
    html.H1("Portfolio Tracker", style={'textAlign': 'center'}),
    html.Div([
        dcc.Input(id='ticker-input', type='text',
                  placeholder='Enter Ticker Symbol', className='three columns'),
        dcc.Input(id='amount-input', type='number',
                  placeholder='Enter Amount in USD', className='three columns'),
        dcc.DatePickerSingle(id='purchase-date-input', placeholder='Select Purchase Date',
                             date=dt.today(), className='three columns'),
        html.Button('Add Investment', id='submit-val',
                    n_clicks=0, className='three columns'),
    ], className='row'),
    dcc.Dropdown(id='pnl-view-selector', options=[
        {'label': 'Global PnL', 'value': 'global'},
        {'label': 'Individual Investments PnL', 'value': 'individual'}
    ], value='global', clearable=False, className='row'),
    html.Div(id='pnl-charts-container', className='row'),
    html.Div(id='investment-list', className='row'),
    html.Div([
        html.Button('Reset Investments', id='reset-button', n_clicks=0),
        html.Button('Export Investments', id='export-button', n_clicks=0),
        dcc.Upload(id='import-button',
                   children=html.Button('Import Investments'), multiple=False),
    ], className='row'),
    dcc.Download(id='download-investment-data'),
    dcc.ConfirmDialog(
        id='confirm-reset', message='Are you sure you want to reset all investments?'),
    dcc.Store(id='investment-storage', storage_type='local'),
], className='container')
# Callback for adding new investments

@app.callback(
    Output('investment-storage', 'data', allow_duplicate=True),
    Input('submit-val', 'n_clicks'),
    [State('investment-storage', 'data'), State('ticker-input', 'value'),
     State('amount-input', 'value'), State('purchase-date-input', 'date')],
    prevent_initial_call=True
)
def add_investment(n_clicks, investments, ticker, amount, purchase_date):
    if investments is None:
        investments = []
    investments.append({'ticker': ticker.upper(), 'amount': amount,
                       'purchase_date': purchase_date, 'closures': []})
    return investments

# Callback for displaying and managing investment list
@app.callback(
    Output('investment-list', 'children', allow_duplicate=True),
    Input('investment-storage', 'data'),
    prevent_initial_call=True
)
def update_investment_list(investments):
    if investments is None:
        raise PreventUpdate

    investment_elements = []
    for i, investment in enumerate(investments):
        open_amount = investment['amount'] - sum(closure['amount']
                                                 for closure in investment.get('closures', []))
        investment_elements.append(html.Div([
            html.P(
                f"{investment['ticker']}: ${open_amount} open (purchased on {investment['purchase_date']})"),
            dcc.Input(id={'type': 'close-amount-input', 'index': i},
                      type='number', placeholder='Enter Amount to Close'),
            dcc.DatePickerSingle(id={'type': 'close-date-input', 'index': i},
                                 placeholder='Select Closing Date', date=dt.today()),
            html.Button('Close Position', id={
                        'type': 'close-position-button', 'index': i}, n_clicks=0),
            html.Div(id={'type': 'close-confirm', 'index': i})
        ], className='row'))

    return investment_elements

# Callback to close a portion of an investment


@app.callback(
    Output({'type': 'close-confirm', 'index': dash.ALL}, 'children'),
    Input({'type': 'close-position-button', 'index': dash.ALL}, 'n_clicks'),
    [State('investment-storage', 'data'),
     State({'type': 'close-amount-input', 'index': dash.ALL}, 'value'),
     State({'type': 'close-date-input', 'index': dash.ALL}, 'date')],
    prevent_initial_call=True
)
def close_investment_position(n_clicks, investments, close_amounts, close_dates):
    if not n_clicks:
        raise PreventUpdate

    ctx = callback_context
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    index = json.loads(button_id)['index']

    investment = investments[index]
    close_amount = close_amounts[index]
    close_date = close_dates[index]

    investment['closures'].append({'amount': close_amount, 'date': close_date})
    return [f"Closed {close_amount} of {investment['ticker']} on {close_date}"] * len(investments)

# Callback for exporting investments


@app.callback(
    Output('download-investment-data', 'data'),
    Input('export-button', 'n_clicks'),
    State('investment-storage', 'data'),
    prevent_initial_call=True
)
def export_investments(n_clicks, investments):
    return dict(content=json.dumps(investments, indent=2), filename='investment_data.json')

# Callback for importing investments


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
        return json.loads(decoded.decode('utf-8'))
    else:
        raise PreventUpdate

# Callback for resetting investments


@app.callback(
    Output('investment-storage', 'data', allow_duplicate=True),
    Input('confirm-reset', 'submit_n_clicks'),
    prevent_initial_call=True
)
def reset_investments(submit_n_clicks):
    return []

# Callback for confirming reset action


@app.callback(
    Output('confirm-reset', 'displayed'),
    Input('reset-button', 'n_clicks'),
    prevent_initial_call=True
)
def display_confirm_reset(n_clicks):
    return True

# Callback to update charts based on stored data``

@app.callback(
    Output('pnl-charts-container', 'children'),
    [Input('investment-storage', 'data'), Input('pnl-view-selector', 'value')],
    prevent_initial_call=True
)
def update_charts(investments, view_selection):
    if investments is None or len(investments) == 0:
        return []

    charts = []
    if view_selection == 'global':
        global_pnl_data = pd.DataFrame()
        for investment in investments:
            ticker_data = yf.Ticker(investment['ticker'])
            df = ticker_data.history(period='1d', start=investment['purchase_date'], end=dt.today().strftime('%Y-%m-%d'))
            
            # Normalize timestamps to ensure consistency
            df.index = pd.to_datetime(df.index.date)
            
            # Forward-fill the Close prices for weekends and holidays
            df['Close'] = df['Close'].fillna(method='ffill')
            
            df['PnL'] = (df['Close'] - df['Close'].iloc[0]) * investment['amount'] / df['Close'].iloc[0]
            df.rename(columns={'PnL': investment['ticker']}, inplace=True)

            if global_pnl_data.empty:
                global_pnl_data = df[[investment['ticker']]]
            else:
                global_pnl_data = global_pnl_data.join(df[[investment['ticker']]], how='outer')

        # Ensure the global PnL data frame is filled for any missing days
        global_pnl_data = global_pnl_data.fillna(method='ffill')

        # Calculate total daily PnL across all investments
        global_pnl_data['Total PnL'] = global_pnl_data.sum(axis=1)

        global_fig = go.Figure(data=go.Scatter(x=global_pnl_data.index, y=global_pnl_data['Total PnL'], mode='lines+markers', name='Total PnL'))
        global_fig.update_layout(title='Global Portfolio PnL', xaxis_title='Date', yaxis_title='Total PnL')
        charts.append(dcc.Graph(figure=global_fig))
    elif view_selection == 'individual':
        for investment in investments:
            ticker_data = yf.Ticker(investment['ticker'])
            df = ticker_data.history(period='1d', start=investment['purchase_date'], end=dt.today().strftime('%Y-%m-%d'))
            
            # Normalize timestamps and forward-fill for weekends and holidays
            df.index = pd.to_datetime(df.index.date)
            df['Close'] = df['Close'].fillna(method='ffill')

            df['PnL'] = (df['Close'] - df['Close'].iloc[0]) * investment['amount'] / df['Close'].iloc[0]
            fig = go.Figure(data=go.Scatter(x=df.index, y=df['PnL'], mode='lines+markers', name=investment['ticker']))
            fig.update_layout(title=f"{investment['ticker']} PnL", xaxis_title='Date', yaxis_title='PnL')
            charts.append(dcc.Graph(figure=fig))

    return charts

if __name__ == '__main__':
    app.run_server(debug=True)
