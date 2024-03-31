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
from pandas import to_datetime, date_range

# To fix:
#  Realized PnL and Unrealized PnL aren't correct. Review the functions.

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
	# Convert ticker to uppercase for consistency
	ticker = ticker.upper()
	# Create a unique identifier for the new position
	position_id = len(investments)
	# Add a new investment entry with the original ticker and a unique position ID
	investments.append({
		'position_id': position_id,
		'original_ticker': ticker,  # Store the original ticker for `yfinance` queries
		'ticker': f"{ticker} {position_id}",  # Use this for display purposes
		'amounts': [amount],
		'purchase_dates': [purchase_date],
		'closures': []
	})
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
		open_amount = sum(investment['amounts']) - sum(closure['amount'] for closure in investment.get('closures', []))
		# Handle multiple purchase dates. You could join them or show the most recent with max()
		purchase_dates_str = ', '.join(investment['purchase_dates'])  # Join all dates into a string
		investment_elements.append(html.Div([
			html.P(f"{investment['ticker']}: ${open_amount} open (purchased on {purchase_dates_str})"),
			dcc.Input(id={'type': 'close-amount-input', 'index': i}, type='number', placeholder='Enter Amount to Close'),
			dcc.DatePickerSingle(id={'type': 'close-date-input', 'index': i}, placeholder='Select Closing Date', date=dt.today()),
			html.Button('Close Position', id={'type': 'close-position-button', 'index': i}, n_clicks=0),
			html.Div(id={'type': 'close-confirm', 'index': i})
		], className='row'))
	return investment_elements

# Callback to close a portion of an investment
@app.callback(
	Output('investment-storage', 'data'),  # Update investment-storage with the modified investments data
	Input({'type': 'close-position-button', 'index': dash.ALL}, 'n_clicks'),
	[State('investment-storage', 'data'),
	 State({'type': 'close-amount-input', 'index': dash.ALL}, 'value'),
	 State({'type': 'close-date-input', 'index': dash.ALL}, 'date')],
	prevent_initial_call=True
)
def close_investment_position(n_clicks, investments, close_amounts, close_dates):
	if not n_clicks or not investments:
		raise PreventUpdate
	ctx = callback_context
	button_id = ctx.triggered[0]['prop_id'].split('.')[0]
	index = json.loads(button_id)['index']
	# Ensure the closure is recorded with 'amount' key
	investment = investments[index]
	close_amount = close_amounts[index]
	# Convert close_date to a consistent date format (e.g., 'YYYY-MM-DD')
	close_date = pd.to_datetime(close_dates[index]).strftime('%Y-%m-%d')
	if close_amount is not None:  # Check if close_amount is not None
		investment['closures'].append({'amount': close_amount, 'date': close_date})
	return investments 

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
	total_invested_amount_global = 0  # For global percentage PnL calculation
	if view_selection == 'individual':
		for investment in investments:
			pnl_data = calculate_individual_pnl(investment, dt.today().strftime('%Y-%m-%d'))
			# Making realized PnL cumulative
			pnl_data['Cumulative Realized PnL'] = pnl_data['Realized PnL'].cumsum()
			total_invested_amount = sum(investment['amounts'])
			total_invested_amount_global += total_invested_amount  # Accumulate for global calculation
			total_realized_pnl = pnl_data['Realized PnL'].sum()
			latest_unrealized_pnl = pnl_data['Unrealized PnL'].iloc[-1]
			total_pnl = total_realized_pnl + latest_unrealized_pnl
			percentage_pnl = (total_pnl / total_invested_amount) * 100
			fig = go.Figure()
			fig.add_trace(go.Scatter(x=pnl_data.index, y=pnl_data['Cumulative Realized PnL'], mode='lines', name='Cumulative Realized PnL', fill='tozeroy', line=dict(color='green')))
			fig.add_trace(go.Scatter(x=pnl_data.index, y=pnl_data['Unrealized PnL'], mode='lines', name='Unrealized PnL', line=dict(color='blue')))
			fig.update_layout(title=f"{investment['ticker']} PnL - Realized: {round(total_realized_pnl)}, Unrealized: {round(latest_unrealized_pnl)}, % PnL: {percentage_pnl:.2f}%", xaxis_title='Date', yaxis_title='PnL')
			charts.append(dcc.Graph(figure=fig))
	elif view_selection == 'global':
		global_pnl_data = pd.DataFrame()
		global_realized_pnl = pd.Series(dtype='float64')
		for investment in investments:
			pnl_data = calculate_individual_pnl(investment, dt.today().strftime('%Y-%m-%d'))
			# Calculate cumulative realized PnL for each investment
			cumulative_realized_pnl = pnl_data['Realized PnL'].cumsum()
			global_realized_pnl = global_realized_pnl.add(cumulative_realized_pnl, fill_value=0)
			total_pnl_series = cumulative_realized_pnl + pnl_data['Unrealized PnL']

			if global_pnl_data.empty:
				global_pnl_data = pd.DataFrame({investment['ticker']: total_pnl_series})
			else:
				global_pnl_data = global_pnl_data.join(pd.DataFrame({investment['ticker']: total_pnl_series}), how='outer')

		global_pnl_data = global_pnl_data.fillna(method='ffill').fillna(0)
		global_pnl_data['Total PnL'] = global_pnl_data.sum(axis=1)
		# get the total invested amount
		total_invested_amount_global = sum(sum(investment['amounts']) for investment in investments)
		# calculate the global percentage PnL
		global_percentage_pnl = (global_pnl_data['Total PnL'].iloc[-1] / total_invested_amount_global) * 100

		global_fig = go.Figure()
		global_fig.add_trace(go.Scatter(x=global_realized_pnl.index, y=global_realized_pnl, mode='lines', name='Total Cumulative Realized PnL', fill='tozeroy', line=dict(color='green')))
		global_fig.add_trace(go.Scatter(x=global_pnl_data.index, y=global_pnl_data['Total PnL'], mode='lines+markers', name='Total PnL', line=dict(color='blue')))
		global_fig.update_layout(title=f"Global Portfolio PnL - PnL = {round(global_percentage_pnl)}%", xaxis_title='Date', yaxis_title='Total PnL')
		charts.append(dcc.Graph(figure=global_fig))
	return charts

def calculate_individual_pnl(investment, end_date):
	ticker_data = yf.Ticker(investment['original_ticker'])
	all_dates = [to_datetime(date).tz_localize('UTC').normalize() for date in investment['purchase_dates']]
	all_dates += [to_datetime(closure['date']).tz_localize('UTC').normalize() for closure in investment.get('closures', [])]
	all_dates.append(to_datetime(end_date).tz_localize('UTC').normalize())
	historical_data = ticker_data.history(start=min(all_dates), end=max(all_dates))
	historical_data.index = historical_data.index.tz_convert('UTC') if historical_data.index.tz is not None else historical_data.index.tz_localize('UTC')
	historical_data.index = historical_data.index.normalize()
	full_date_range = date_range(start=min(all_dates), end=max(all_dates), freq='D')
	historical_data = historical_data.reindex(full_date_range, method='ffill')

	# Initialize new columns
	historical_data['Purchase Price'] = 0.0
	historical_data['Amount'] = 0.0
	historical_data['Realized PnL'] = 0.0
	historical_data['Unrealized PnL'] = 0.0

	total_amount = 0  # Track the total amount after each purchase and closure
	for i, purchase_date in enumerate(investment['purchase_dates']):
		purchase_date = to_datetime(purchase_date).tz_localize('UTC').normalize()
		amount = investment['amounts'][i]
		total_amount += amount  # Update total amount
		if purchase_date in historical_data.index:
			purchase_price = historical_data.at[purchase_date, 'Close']
			# Update Purchase Price and Amount from the purchase date onwards
			historical_data.loc[purchase_date:, 'Purchase Price'] = purchase_price
			historical_data.loc[purchase_date:, 'Amount'] += amount

	for closure in investment.get('closures', []):
		closure_date = to_datetime(closure['date']).tz_localize('UTC').normalize()
		closure_amount = closure['amount']
		total_amount -= closure_amount  # Update total amount
		if closure_date in historical_data.index:
			closure_price = historical_data.at[closure_date, 'Close']
			# Calculate Realized PnL for the closure
			realized_pnl = (closure_price - purchase_price) * closure_amount / purchase_price
			historical_data.at[closure_date, 'Realized PnL'] += realized_pnl
			# Adjust Amount column post-closure
			historical_data.loc[closure_date:, 'Amount'] -= closure_amount

	# Calculate Unrealized PnL
	historical_data['Unrealized PnL'] = historical_data['Amount'] / historical_data['Purchase Price'] * (historical_data['Close'] - historical_data['Purchase Price'])

	return historical_data[['Purchase Price', 'Amount', 'Realized PnL', 'Unrealized PnL']]

if __name__ == '__main__':
	app.run_server(debug=True)
