from flask import render_template, request
from flask_login import login_required
from app import app
from app.functions.mosys import get_pervasive
import pandas as pd
import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Column label mapping for user-friendly display
COLUMN_LABELS = {
    'DATA_RILEVAMENTO': 'Measurement date',
    'ORA_RILEVAMENTO': 'Measurement time',
    'DESCRIZIONE': 'Drawing specification',
    'NUMERO_STAMPATA': 'Shot number',
    'NUMERO_FIGURA': 'Cavity number',
    'MIS01': 'Measurement 1',
    'MIS02': 'Measurement 2',
    'MIS03': 'Measurement 3',
    'MIS04': 'Measurement 4',
    'MIS05': 'Measurement 5',
    'MIS06': 'Measurement 6',
    'MIS07': 'Measurement 7',
    'MIS08': 'Measurement 8',
    'MIS09': 'Measurement 9',
    'MIS10': 'Measurement 10'
}

@app.route('/')
@app.route('/index')
@login_required
def index():
    logger.info("=== INDEX ROUTE CALLED ===")
    
    # Define columns based on spec - ARTICOLO removed, DESCRIZIONE replaces NUMERO_RIFERIMENTO
    table_columns = [
        'DATA_RILEVAMENTO', 'ORA_RILEVAMENTO', 'DESCRIZIONE', 
        'NUMERO_STAMPATA', 'NUMERO_FIGURA', 'MIS01', 'MIS02', 'MIS03', 
        'MIS04', 'MIS05', 'MIS06', 'MIS07', 'MIS08', 'MIS09', 'MIS10'
    ]
    
    results_columns = [
        'MIS01', 'MIS02', 'MIS03', 'MIS04', 'MIS05', 
        'MIS06', 'MIS07', 'MIS08', 'MIS09', 'MIS10'
    ]

    # Get filter parameters
    articolo = request.args.get('articolo')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    numero_riferimento = request.args.get('numero_riferimento')
    action = request.args.get('action')
    
    logger.info(f"Parameters: articolo={articolo}, date_from={date_from}, date_to={date_to}, numero_rif={numero_riferimento}, action={action}")

    # Fetch NSCHEDIM data for dropdown (filtered by ARTICOLO if provided)
    # OPTIMIZATION: Fetch all NSCHEDIM data once, filter in Python (much faster than INNER JOIN)
    if action == 'fetch':
        try:
            logger.info("Fetching NSCHEDIM dropdown data...")
            # Simple query without JOIN - much faster
            nschedim_query = "SELECT NUMERO_RIFERIMENTO, DESCRIZIONE, FLAG_RIMOSSO FROM STAAMPDB.NSCHEDIM"
            nschedim_df = get_pervasive(nschedim_query)
            logger.info(f"Fetched {len(nschedim_df)} total NSCHEDIM records")
            
            # If articolo is provided, we'll filter dropdown options after getting main data
            # For now, provide all options (will be filtered by main query results)
            riferimento_options = nschedim_df.to_dict('records')
            logger.info(f"Prepared {len(riferimento_options)} dropdown options")
        except Exception as e:
            logger.error(f"Error fetching NSCHEDIM data: {e}")
            riferimento_options = []
    else:
        riferimento_options = []
        logger.info("Skipping NSCHEDIM fetch (not needed)")

    # If action is not 'fetch', return empty data (initial load) with dropdown options
    if action != 'fetch':
        logger.info("Action is not 'fetch', returning empty data")
        return render_template('index.html', title='MOSYS: COLLAUDO-10-2 measurement records', columns=table_columns, data=None, riferimento_options=riferimento_options)

    # Build query dynamically with NSCHEDIM join
    logger.info("Building main query...")
    query_parts = [
        "SELECT NRILDIM.*, NSCHEDIM.DESCRIZIONE ",
        "FROM STAAMPDB.NRILDIM NRILDIM ",
        "LEFT JOIN STAAMPDB.NSCHEDIM NSCHEDIM ON NRILDIM.NUMERO_RIFERIMENTO = NSCHEDIM.NUMERO_RIFERIMENTO ",
        "WHERE 1=1"
    ]
    params = []

    if articolo:
        query_parts.append("AND NRILDIM.ARTICOLO LIKE ?")
        params.append(f"{articolo}%")
    
    if numero_riferimento:
        query_parts.append("AND NRILDIM.NUMERO_RIFERIMENTO = ?")
        params.append(numero_riferimento)
    
    if date_from:
        d_from = date_from.replace('-', '')
        query_parts.append("AND NRILDIM.DATA_RILEVAMENTO >= ?")
        params.append(d_from)
    
    if date_to:
        d_to = date_to.replace('-', '')
        query_parts.append("AND NRILDIM.DATA_RILEVAMENTO <= ?")
        params.append(d_to)

    if not date_from and not date_to and not articolo and not numero_riferimento:
         query_parts.append("AND NRILDIM.DATA_RILEVAMENTO LIKE '2025%'")

    query = " ".join(query_parts)
    logger.info(f"Query: {query}")
    logger.info(f"Params: {params}")
    
    try:
        logger.info("Executing database query...")
        df = get_pervasive(query, params=tuple(params))
        logger.info(f"Query returned {len(df)} rows with columns: {df.columns.tolist()}")
        
    except Exception as e:
        logger.error(f"DB Error: {e}", exc_info=True)
        # Mock data fallback (simplified)
        data = {
            'ARTICOLO': ['ART-001', 'ART-002', 'ART-003'],
            'DATA_RILEVAMENTO': ['20250101', '20250102', '20241231'],
            'ORA_RILEVAMENTO': ['10:00', '11:00', '12:00'],
            'DESCRIZIONE': ['Dim 1', 'Dim 2', 'Dim 3'],
            'NUMERO_STAMPATA': ['1', '2', '3'],
            'NUMERO_FIGURA': ['1', '1', '2'],
            'MIS01': [10500, 10600, 10000],
            'MIS02': [20000, 20100, 20000],
        }
        df = pd.DataFrame(data)
        logger.info("Using mock data fallback")

    # OPTIMIZATION 1: Vectorized date formatting (much faster than .apply())
    logger.info("Formatting dates...")
    if 'DATA_RILEVAMENTO' in df.columns:
        df['DATA_RILEVAMENTO'] = df['DATA_RILEVAMENTO'].astype(str).str.strip()
        mask = df['DATA_RILEVAMENTO'].str.len() == 8
        df.loc[mask, 'DATA_RILEVAMENTO'] = (
            df.loc[mask, 'DATA_RILEVAMENTO'].str[:4] + '-' + 
            df.loc[mask, 'DATA_RILEVAMENTO'].str[4:6] + '-' + 
            df.loc[mask, 'DATA_RILEVAMENTO'].str[6:8]
        )
        logger.info(f"Formatted {mask.sum()} dates")

    # Format ORA_RILEVAMENTO to HH:MM:SS
    logger.info("Formatting time...")
    if 'ORA_RILEVAMENTO' in df.columns:
        df['ORA_RILEVAMENTO'] = df['ORA_RILEVAMENTO'].astype(str).str.strip()
        # Assuming format is HHMMSS or HH:MM:SS already
        mask_time = df['ORA_RILEVAMENTO'].str.len() == 6
        df.loc[mask_time, 'ORA_RILEVAMENTO'] = (
            df.loc[mask_time, 'ORA_RILEVAMENTO'].str[:2] + ':' + 
            df.loc[mask_time, 'ORA_RILEVAMENTO'].str[2:4] + ':' + 
            df.loc[mask_time, 'ORA_RILEVAMENTO'].str[4:6]
        )
        logger.info(f"Formatted {mask_time.sum()} times")
    
    # Extract last digit from NUMERO_STAMPATA and NUMERO_FIGURA
    logger.info("Formatting NUMERO_STAMPATA and NUMERO_FIGURA...")
    if 'NUMERO_STAMPATA' in df.columns:
        df['NUMERO_STAMPATA'] = df['NUMERO_STAMPATA'].astype(str).str.strip().str[-1:]
    if 'NUMERO_FIGURA' in df.columns:
        df['NUMERO_FIGURA'] = df['NUMERO_FIGURA'].astype(str).str.strip().str[-1:]

    # OPTIMIZATION 2: Batch process all MIS columns at once (much faster than looping)
    logger.info("Processing MIS columns...")
    mis_cols_in_df = [col for col in results_columns if col in df.columns]
    if mis_cols_in_df:
        df[mis_cols_in_df] = df[mis_cols_in_df].apply(pd.to_numeric, errors='coerce')
        df[mis_cols_in_df] = df[mis_cols_in_df] / 10000.0
        # Format to 3 decimal places (will be done in template for display)
        logger.info(f"Processed {len(mis_cols_in_df)} MIS columns")

    # Filter out empty results columns (columns that are all NaN or empty)
    valid_results_cols = [col for col in results_columns if col in df.columns and df[col].notna().any()]
    logger.info(f"Valid MIS columns: {valid_results_cols}")
    
    # OPTIMIZATION: Filter dropdown options to only show NUMERO_RIFERIMENTO values present in results
    if riferimento_options and 'NUMERO_RIFERIMENTO' in df.columns:
        unique_refs = df['NUMERO_RIFERIMENTO'].dropna().unique().tolist()
        logger.info(f"Found {len(unique_refs)} unique NUMERO_RIFERIMENTO in results")
        # Filter dropdown to only include options that exist in results
        riferimento_options = [opt for opt in riferimento_options if opt['NUMERO_RIFERIMENTO'] in unique_refs]
        logger.info(f"Filtered dropdown to {len(riferimento_options)} relevant options")
    
    # Reconstruct table_columns to only include valid result columns + other columns
    final_columns = [c for c in table_columns if c not in results_columns] + valid_results_cols
    
    # Ensure all final columns exist in df
    final_columns = [c for c in final_columns if c in df.columns]
    logger.info(f"Final columns: {final_columns}")
    
    # OPTIMIZATION 3: Use 'records' orient but only for final columns (reduces memory)
    data = df[final_columns].to_dict(orient='records')
    logger.info(f"Converted to {len(data)} records for template")
    
    logger.info("=== RENDERING TEMPLATE ===")
    return render_template('index.html', title='MOSYS: COLLAUDO-10-2 measurement records', columns=final_columns, data=data, riferimento_options=riferimento_options, column_labels=COLUMN_LABELS)

@app.route('/graph')
@login_required
def graph():
    logger.info("=== GRAPH ROUTE CALLED ===")
    
    # Get filter parameters
    articolo = request.args.get('articolo')
    numero_riferimento = request.args.get('numero_riferimento')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    logger.info(f"Graph params: articolo={articolo}, numero_rif={numero_riferimento}, date_from={date_from}, date_to={date_to}")
    
    # Build query
    query_parts = [
        "SELECT NRILDIM.*, NSCHEDIM.DESCRIZIONE, NSCHEDIM.VALORE_NOMINALE ",
        "FROM STAAMPDB.NRILDIM NRILDIM ",
        "LEFT JOIN STAAMPDB.NSCHEDIM NSCHEDIM ON NRILDIM.NUMERO_RIFERIMENTO = NSCHEDIM.NUMERO_RIFERIMENTO ",
        "WHERE 1=1"
    ]
    params = []
    
    if articolo:
        query_parts.append("AND NRILDIM.ARTICOLO LIKE ?")
        params.append(f"{articolo}%")
    
    if numero_riferimento:
        query_parts.append("AND NRILDIM.NUMERO_RIFERIMENTO = ?")
        params.append(numero_riferimento)
    
    if date_from:
        d_from = date_from.replace('-', '')
        query_parts.append("AND NRILDIM.DATA_RILEVAMENTO >= ?")
        params.append(d_from)
    
    if date_to:
        d_to = date_to.replace('-', '')
        query_parts.append("AND NRILDIM.DATA_RILEVAMENTO <= ?")
        params.append(d_to)
    
    query_parts.append("ORDER BY NRILDIM.DATA_RILEVAMENTO, NRILDIM.ORA_RILEVAMENTO")
    query = " ".join(query_parts)
    
    logger.info(f"Graph query: {query}")
    logger.info(f"Params: {params}")
    
    try:
        df = get_pervasive(query, params=tuple(params))
        logger.info(f"Graph query returned {len(df)} rows")
    except Exception as e:
        logger.error(f"Graph DB Error: {e}", exc_info=True)
        return render_template('graph.html', title='Measurement records chart', error="Error fetching data from database")
    
    if df.empty:
        return render_template('graph.html', title='Measurement records chart', error="No data found for selected filters")
    
    # Process data for graph
    results_columns = ['MIS01', 'MIS02', 'MIS03', 'MIS04', 'MIS05', 'MIS06', 'MIS07', 'MIS08', 'MIS09', 'MIS10']
    
    # Convert MIS columns to numeric
    mis_cols_in_df = [col for col in results_columns if col in df.columns]
    if mis_cols_in_df:
        df[mis_cols_in_df] = df[mis_cols_in_df].apply(pd.to_numeric, errors='coerce')
        df[mis_cols_in_df] = df[mis_cols_in_df] / 10000.0
    
    # Calculate average MIS value per row (only non-NaN values)
    df['MIS_AVG'] = df[mis_cols_in_df].mean(axis=1, skipna=True)
    
    # Create datetime column
    df['DATA_RILEVAMENTO'] = df['DATA_RILEVAMENTO'].astype(str).str.strip()
    df['ORA_RILEVAMENTO'] = df['ORA_RILEVAMENTO'].astype(str).str.strip().str.zfill(6)
    df['DATETIME'] = df['DATA_RILEVAMENTO'] + ' ' + df['ORA_RILEVAMENTO'].str[:2] + ':' + df['ORA_RILEVAMENTO'].str[2:4] + ':' + df['ORA_RILEVAMENTO'].str[4:6]
    
    # Get unique NUMERO_FIGURA values
    numero_figura_values = df['NUMERO_FIGURA'].dropna().unique().tolist()
    logger.info(f"Found {len(numero_figura_values)} unique NUMERO_FIGURA values: {numero_figura_values}")
    
    # Get VALORE_NOMINALE and tolerance data from SCHEDIM1 for Cp/Cpk calculation
    valore_nominale = None
    usl = None  # Upper Specification Limit
    lsl = None  # Lower Specification Limit
    
    # Fetch tolerance data from SCHEDIM1 table
    if numero_riferimento:
        try:
            logger.info(f"Fetching tolerance data for NUMERO_RIFERIMENTO: {numero_riferimento}")
            query_tolerance = """
            SELECT CODICE_ARTICOLO, RIF_MISURA, UN_MIS, VALORE_NOMINALE, SEGNO_TOLL_INF, TOLL_INF, SEGNO_TOLL_SUP, TOLL_SUP
            FROM STAAMPDB.SCHEDIM1 SCHEDIM1
            WHERE SCHEDIM1.RIF_MISURA = ?
            """
            tolerance_df = get_pervasive(query_tolerance, params=(numero_riferimento,))
            logger.info(f"Tolerance query returned {len(tolerance_df)} rows")
            
            if not tolerance_df.empty:
                # Get tolerance values from first row
                tol_row = tolerance_df.iloc[0]
                valore_nominale = float(tol_row['VALORE_NOMINALE']) if pd.notna(tol_row['VALORE_NOMINALE']) else None
                
                # Parse tolerance operators and values
                segno_toll_inf = str(tol_row['SEGNO_TOLL_INF']).strip() if pd.notna(tol_row['SEGNO_TOLL_INF']) else '+'
                toll_inf = float(tol_row['TOLL_INF']) if pd.notna(tol_row['TOLL_INF']) else 0
                segno_toll_sup = str(tol_row['SEGNO_TOLL_SUP']).strip() if pd.notna(tol_row['SEGNO_TOLL_SUP']) else '+'
                toll_sup = float(tol_row['TOLL_SUP']) if pd.notna(tol_row['TOLL_SUP']) else 0
                
                logger.info(f"Tolerance data: VALORE_NOMINALE={valore_nominale}, SEGNO_TOLL_INF={segno_toll_inf}, TOLL_INF={toll_inf}, SEGNO_TOLL_SUP={segno_toll_sup}, TOLL_SUP={toll_sup}")
                
                # Calculate USL and LSL based on operators
                # Note: Tolerance values are already in correct scale (not divided by 10000)
                if valore_nominale is not None:
                    # Calculate both limits using the operators
                    # TOLL_INF calculation
                    if segno_toll_inf == '-':
                        limit_inf = valore_nominale - toll_inf
                    elif segno_toll_inf == '+':
                        limit_inf = valore_nominale + toll_inf
                    else:
                        limit_inf = valore_nominale - toll_inf  # Default to minus
                    
                    # TOLL_SUP calculation
                    if segno_toll_sup == '-':
                        limit_sup = valore_nominale - toll_sup
                    elif segno_toll_sup == '+':
                        limit_sup = valore_nominale + toll_sup
                    else:
                        limit_sup = valore_nominale + toll_sup  # Default to plus
                    
                    # Ensure USL > LSL (swap if needed, as naming might be confusing)
                    usl = max(limit_inf, limit_sup)
                    lsl = min(limit_inf, limit_sup)
                    
                    logger.info(f"Calculated limits: LSL={lsl}, USL={usl}, Nominal={valore_nominale}")
        except Exception as e:
            logger.error(f"Error fetching tolerance data: {e}", exc_info=True)
            # Fallback to NSCHEDIM if SCHEDIM1 query fails
            if 'VALORE_NOMINALE' in df.columns and df['VALORE_NOMINALE'].notna().any():
                valore_nominale = df['VALORE_NOMINALE'].iloc[0]
                try:
                    valore_nominale = float(valore_nominale)
                    logger.info(f"VALORE_NOMINALE from NSCHEDIM: {valore_nominale}")
                except:
                    valore_nominale = None
    
    # Calculate Cp and Cpk for each NUMERO_FIGURA separately
    capability_data = {}
    
    # Only calculate Cp/Cpk if we have actual tolerance limits from database
    if usl is not None and lsl is not None:
        for figura in numero_figura_values:
            figura_df = df[df['NUMERO_FIGURA'] == figura].copy()
            mis_values = figura_df['MIS_AVG'].dropna()
            
            if len(mis_values) > 1:
                mean = mis_values.mean()
                std = mis_values.std()
                
                logger.info(f"NUMERO_FIGURA {figura}: Mean={mean}, Std={std}")
                
                if std > 0:
                    # Calculate Cp (Process Capability) using database limits
                    cp = (usl - lsl) / (6 * std)
                    
                    # Calculate Cpk (Process Capability Index) using database limits
                    cpu = (usl - mean) / (3 * std)
                    cpl = (mean - lsl) / (3 * std)
                    cpk = min(cpu, cpl)
                    
                    capability_data[str(figura)] = {
                        'cp': round(cp, 3),
                        'cpk': round(cpk, 3),
                        'mean': round(mean, 3),
                        'std': round(std, 3)
                    }
                    
                    logger.info(f"NUMERO_FIGURA {figura}: Cp={cp:.3f}, Cpk={cpk:.3f} (using database limits USL={usl}, LSL={lsl})")
    else:
        logger.warning("No tolerance limits available from SCHEDIM1 - skipping Cp/Cpk calculation")
    
    # Prepare data for Chart.js
    import json
    chart_data = {}
    
    for figura in numero_figura_values:
        figura_df = df[df['NUMERO_FIGURA'] == figura].copy()
        figura_df = figura_df.dropna(subset=['MIS_AVG'])
        
        chart_data[str(figura)] = {
            'labels': figura_df['DATETIME'].tolist(),
            'values': figura_df['MIS_AVG'].round(3).tolist()
        }
    
    chart_data_json = json.dumps(chart_data)
    descrizione = df['DESCRIZIONE'].iloc[0] if 'DESCRIZIONE' in df.columns else numero_riferimento
    
    logger.info(f"Prepared chart data for {len(chart_data)} NUMERO_FIGURA values")
    
    return render_template('graph.html', 
                         title='Measurement records chart', 
                         chart_data=chart_data_json,
                         descrizione=descrizione,
                         numero_figura_count=len(numero_figura_values),
                         valore_nominale=valore_nominale,
                         usl=usl,
                         lsl=lsl,
                         capability_data=json.dumps(capability_data),
                         column_labels=COLUMN_LABELS)
