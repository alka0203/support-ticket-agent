"""One-off script that assembles and executes notebooks/01_explore.ipynb.
Not part of the app; run once to regenerate the notebook with fresh outputs.
"""
import nbformat as nbf
from nbclient import NotebookClient

cells = []

cells.append(nbf.v4.new_markdown_cell(
    "# Step 5 — Explore the raw ticket data\n"
    "Support Ticket Insights Agent — Phase 2, Step 5.\n\n"
    "Goal: look at columns/types, missing values, duplicates, value distributions, "
    "and a handful of raw rows read by eye, before designing the clean data model (Step 7)."
))

cells.append(nbf.v4.new_code_cell(
    "import pandas as pd\n"
    "pd.set_option('display.max_columns', None)\n"
    "pd.set_option('display.width', 140)\n"
    "df = pd.read_csv('../data/raw/customer_support_tickets.csv')\n"
    "df.shape"
))

cells.append(nbf.v4.new_markdown_cell("## Columns and dtypes"))
cells.append(nbf.v4.new_code_cell("df.dtypes"))

cells.append(nbf.v4.new_markdown_cell("## Missing values per column"))
cells.append(nbf.v4.new_code_cell(
    "missing = df.isna().sum().sort_values(ascending=False)\n"
    "missing_pct = (missing / len(df) * 100).round(1)\n"
    "pd.DataFrame({'missing_count': missing, 'missing_pct': missing_pct})"
))

cells.append(nbf.v4.new_markdown_cell(
    "## Blank strings (not NaN, but empty) — CSVs often hide these\n"
    "Some columns showed as non-null in a quick head() but were empty strings, e.g. `Resolution`."
))
cells.append(nbf.v4.new_code_cell(
    "blank = (df.astype(str).apply(lambda s: s.str.strip()) == '').sum().sort_values(ascending=False)\n"
    "blank[blank > 0]"
))

cells.append(nbf.v4.new_markdown_cell("## Duplicates"))
cells.append(nbf.v4.new_code_cell(
    "print('duplicate Ticket ID rows:', df['Ticket ID'].duplicated().sum())\n"
    "print('fully duplicate rows:', df.duplicated().sum())\n"
    "print('duplicate (Customer Email, Ticket Subject, Ticket Description) rows:',\n"
    "      df.duplicated(subset=['Customer Email', 'Ticket Subject', 'Ticket Description']).sum())"
))

cells.append(nbf.v4.new_markdown_cell("## Categorical value distributions"))
cells.append(nbf.v4.new_code_cell(
    "for col in ['Ticket Type', 'Ticket Status', 'Ticket Priority', 'Ticket Channel', 'Customer Gender']:\n"
    "    print(f'--- {col} ---')\n"
    "    print(df[col].value_counts(dropna=False))\n"
    "    print()"
))

cells.append(nbf.v4.new_markdown_cell("## Product Purchased — how many distinct products, and top counts"))
cells.append(nbf.v4.new_code_cell(
    "print('distinct products:', df['Product Purchased'].nunique())\n"
    "df['Product Purchased'].value_counts().head(15)"
))

cells.append(nbf.v4.new_markdown_cell("## Date fields — ranges and formats"))
cells.append(nbf.v4.new_code_cell(
    "for col in ['Date of Purchase', 'First Response Time', 'Time to Resolution']:\n"
    "    parsed = pd.to_datetime(df[col], errors='coerce')\n"
    "    print(f'--- {col} ---')\n"
    "    print('non-null:', parsed.notna().sum(), '/', len(df))\n"
    "    print('min:', parsed.min(), ' max:', parsed.max())\n"
    "    print()"
))

cells.append(nbf.v4.new_markdown_cell(
    "**Note:** `First Response Time` and `Time to Resolution` should be checked for whether they cluster "
    "on a single day (a red flag that they're generation timestamps, not real activity times)."
))
cells.append(nbf.v4.new_code_cell(
    "resp = pd.to_datetime(df['First Response Time'], errors='coerce')\n"
    "print('distinct calendar dates in First Response Time:', resp.dt.date.nunique())\n"
    "res = pd.to_datetime(df['Time to Resolution'], errors='coerce')\n"
    "print('distinct calendar dates in Time to Resolution:', res.dt.date.nunique())"
))

cells.append(nbf.v4.new_markdown_cell("## Customer Satisfaction Rating — only present for closed tickets?"))
cells.append(nbf.v4.new_code_cell(
    "pd.crosstab(df['Ticket Status'], df['Customer Satisfaction Rating'].isna(), rownames=['Status'], colnames=['Rating is NaN'])"
))

cells.append(nbf.v4.new_markdown_cell("## Ticket Description — check for the templated `{product_purchased}` placeholder"))
cells.append(nbf.v4.new_code_cell(
    "has_placeholder = df['Ticket Description'].str.contains(r'\\{product_purchased\\}', regex=True, na=False)\n"
    "print('rows with literal {product_purchased} placeholder:', has_placeholder.sum(), '/', len(df))\n"
    "print('pct:', round(has_placeholder.mean() * 100, 1), '%')"
))

cells.append(nbf.v4.new_markdown_cell("## Resolution text — spot check for templated/gibberish text"))
cells.append(nbf.v4.new_code_cell(
    "df.loc[df['Resolution'].notna() & (df['Resolution'].str.strip() != ''), 'Resolution'].sample(8, random_state=0).tolist()"
))

cells.append(nbf.v4.new_markdown_cell("## Raw rows, read by eye"))
cells.append(nbf.v4.new_code_cell(
    "with pd.option_context('display.max_colwidth', 200):\n"
    "    display(df.sample(5, random_state=1)[['Ticket ID', 'Ticket Type', 'Ticket Subject', 'Ticket Description', 'Ticket Status', 'Resolution']])"
))

nb = nbf.v4.new_notebook(cells=cells)
nb.metadata = {
    "kernelspec": {"display_name": "Python 3 (venv)", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

client = NotebookClient(nb, timeout=120, kernel_name="python3", resources={"metadata": {"path": "notebooks/"}})
client.execute()

with open("notebooks/01_explore.ipynb", "w") as f:
    nbf.write(nb, f)

print("Wrote notebooks/01_explore.ipynb with executed outputs.")
