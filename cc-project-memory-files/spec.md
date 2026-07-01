## Project Name
MOSYS wyniki pomiarów
 
## Project Description
Serves as a web interface for displaying the results of measurements resutls stored in the Pervasive database of the MOSYS system.

## MOSYS database connection function to be used in all modules
function pervasive_connection() @app.functions.mosys.py

## MOSYS function to get data from the database
function get_pervasive(query: str, params: tuple = None) -> pd.DataFrame @app.functions.mosys.py

## queries to be used in the application
# Connection with results table
query_results = """
SELECT *
FROM STAAMPDB.NRILDIM NRILDIM
WHERE NRILDIM.DATA_RILEVAMENTO = ?
"""


# Table columns to be displayed
table_columns = [
ARTICOLO, DATA_RILEVAMENTO, ORA_RILEVAMENTO, NUMERO_RIFERIMENTO, NUMERO_STAMPATA, NUMERO_FIGURA, MIS01, MIS02, MIS03, MIS04, MIS05, MIS06, MIS07, MIS08, MIS09, MIS10
]
**Note: only not rows where DATA_RILEVAMENTO starts with '2025' should be displayed.**

# Results columns:
results_columns = [
MIS01, MIS02, MIS03, MIS04, MIS05, MIS06, MIS07, MIS08, MIS09, MIS10
]
**Note:
If the values are strings, they should be converted to numbers and divided by 1000 before being displayed.
If the values are numbers, they should be only divided by 1000 before being displayed.
**

**pandas library should be used for data manipulation and display.**

## Resutls table view
Modern UI should be used for the results table view. Each column header should be clickable and sorted in ascending or descending order. The table should be scrollable and have a fixed height. The table should have a search bar to search for specific results for each column. Search bars placed inside column headers (on the bottom). Searching while typing should be implemented.
**NOTE: the search bar should be case-insensitive.**
**NOTE: only not empty results_columns should be displayed in the table.**

## data base tables with relationships to main data table

### Table: NSCHEDIM
query_nschedim = """
SELECT NUMERO_RIFERIMENTO, CODICE_CONTROLLO, DESCRIZIONE, NUMERO_STAMPATE, TIPO_CONTROLLO, FREQUENZA_MINUTI, CODICE_STRUMENTO, FLAG_MODO_INSER, UN_MIS, VALORE_NOMINALE, DATA_AGGIORNAMENTO, OPERATORE_AGG, NUMERO_MISURE_PER_C, FLAG_RIMOSSO, NOTE
FROM STAAMPDB.NSCHEDIMM NSCHEDIM
WHERE NSCHEDIM.NUMERO_RIFERIMENTO = ? AND NSCHEDIM.FLAG_RIMOSSO != {look-up MOSYS-db for least occuring value and put into query here}.
"""
# FLAG_RIMOSSO = least occuring value in MOSYS.NSCHEDIM - such flagged table-row = dimension removed (characteristic excluded from control plan)   
# Column NUMERO_RIFERIMENTO is a foreign key to NRILDIM.NUMERO_RIFERIMENTO
# Column DESCRIZIONE is a description of drawing dimensions, which is used to display the description of the drawing dimensions in the results table as well as for the dropbox list in the filter of column header NUMERO_RIFERIMENTO (to replace existing text field for this column)

## when loading spin displayed, hide the container with label 'Please use the filters above and click "Get Data" to view results.'

## main table additional features
# ORA_RILEVAMENTO column should be displayed in 'HH:MM:SS' format.
# Column ARTICOLO should be removed from the table.
# MIS columns when no data - should be displayed as empty.
# MIS columns when data is available - should be displayed always with 3 decimal places.
# MIS columns should be displayed in green color if the value is close to VALORE_NOMINALE (close means within 2*SIGMA).
# NUMERO_STAMPATA and NUMERO_FIGURA columns values should be formatted by removing prefix "00" (parsed only last digit)  
 

## tolerance reference database table
query_tolerance = """
SELECT CODICE_ARTICOLO, RIF_MISURA, UN_MIS, VALORE_NOMINALE, SEGNO_TOLL_INF, TOLL_INF, SEGNO_TOLL_SUP, TOLL_SUP
FROM STAAMPDB.SCHEDIM1 SCHEDIM1
WHERE SCHEDIM1.RIF_MISURA = ?
"""
# Column RIF_MISURA is a foreign key to NSCHEDIM.NUMERO_RIFERIMENTO
# Column SEGNO_TOLL_INF is operator for upper tolerance calculation from VALORE_NOMINALE
# Column TOLL_INF is upper tolerance value
# VALORE_NOMINALE <operator SEGNO_TOLL_INF (e.g. + or -)> TOLL_INF = upper tolerance limit
# Column SEGNO_TOLL_SUP is operator for lower tolerance calculation from VALORE_NOMINALE
# Column TOLL_SUP is lower tolerance value
# VALORE_NOMINALE <operator SEGNO_TOLL_SUP (e.g. + or -)> TOLL_SUP = lower tolerance limit

## Table columns aliases (captions) for displaing the table headers
# DATA_RILEVAMENTO -> Date
# ORA_RILEVAMENTO -> Time
# DESCRIZIONE -> Dimension
# NUMERO_STAMPATA -> Shot
# NUMERO_FIGURA -> Cavity
# MIS01 -> Result 1
# MIS02 -> Result 2
# MIS03 -> Result 3
# MIS04 -> Result 4
# MIS05 -> Result 5
# MIS06 -> Result 6
# MIS07 -> Result 7
# MIS08 -> Result 8
# MIS09 -> Result 9
# MIS10 -> Result 10

***IMPORTANT! all statistic calculations must be conducted per each set of measurement results values groupped and separeted by multi-index of columns 'NUMERO_STAMPATA' and 
'NUMERO_FIGURA' join string-values. For more details and master-reference code and for statistic functions and for MOSYS-db tables schema deduction, READ queries, data-display 
logic and conventions, take context from existing @app/routes.py file.