import os
import json
import yaml
import logging
import smtplib
import yfinance as yf
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 1. Charger les variables d’environnement
def load_env():
    load_dotenv()
    return {
        'EMAIL_SENDER': os.getenv('EMAIL_EXPEDITEUR'),
        'EMAIL_PASSWORD': os.getenv('EMAIL_MDP'),
        'EMAIL_RECIPIENT': os.getenv('EMAIL_DESTINATAIRE')
    }

# 2. Charger la config YAML
def load_config(path='config.yaml'):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# 3. Récupérer les données de marché
def fetch_price_data(ticker, period, interval):
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    return df if not df.empty else None

# 4. Calculer les indicateurs (MA, RSI, volume moyen)
def compute_indicators(df, cfg):
    df['MA_short'] = df['Close'].rolling(window=cfg['ma_short']).mean()
    df['MA_long']  = df['Close'].rolling(window=cfg['ma_long']).mean()
    df['Volume_avg'] = df['Volume'].rolling(window=cfg['volume_window']).mean()

    # RSI
    delta     = df['Close'].diff()
    gain      = delta.where(delta > 0, 0.0)
    loss      = -delta.where(delta < 0, 0.0)
    avg_gain  = gain.rolling(window=cfg['rsi_period']).mean()
    avg_loss  = loss.rolling(window=cfg['rsi_period']).mean()
    rs        = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    return df.dropna()

# 5. Attribuer un score
def score_stock(latest, cfg):
    score   = 0
    weighted = 0.0
    rsi     = latest['RSI']
    ma_short = latest['MA_short']
    ma_long  = latest['MA_long']
    vol      = latest['Volume']
    vol_avg  = latest['Volume_avg']

    # RSI
    if rsi < cfg['rsi_oversold']:
        score += 1
        weighted += cfg['weights']['rsi_oversold']
    elif rsi < cfg['rsi_neutral']:
        score += 1
        weighted += cfg['weights']['rsi_neutral']

    # Croisement de moyennes
    if ma_short > ma_long:
        score += 1
        weighted += cfg['weights']['ma_crossover']

    # Volume
    if vol > cfg['volume_boost'] * vol_avg:
        score += 1
        weighted += cfg['weights']['volume_boost']

    return score, round(weighted, 1)

# 6. Générer stop loss et objectifs
def generate_targets(price, cfg):
    stop = round(price * (1 - cfg['stop_loss_pct']), 2)
    tgt1 = round(price * (1 + cfg['target1_pct']), 2)
    tgt2 = round(price * (1 + cfg['target2_pct']), 2)
    rr   = round((price * cfg['target1_pct']) / (price * cfg['stop_loss_pct']), 2)
    return stop, tgt1, tgt2, rr

# 7. Construire le DataFrame des opportunités
def prepare_opportunities(mapping, cfg):
    rows = []
    for ticker, meta in mapping.items():
        try:
            df = fetch_price_data(ticker, cfg['data_period'], cfg['data_interval'])
            if df is None or len(df) < cfg['min_data_points']:
                continue

            df_ind = compute_indicators(df, cfg)
            latest = df_ind.iloc[-1]
            score, weighted = score_stock(latest, cfg)
            if score < cfg['min_score']:
                continue

            price = latest['Close']
            stop, tgt1, tgt2, rr = generate_targets(price, cfg)

            # Avis selon RSI
            rsi = latest['RSI']
            if rsi < cfg['rsi_oversold']:
                avis = 'RSI < 30 ✅'
            elif rsi > cfg['rsi_overbought']:
                avis = 'RSI > 70 ⚠️'
            else:
                avis = 'RSI neutre'

            rows.append({
                'Ticker': ticker,
                'Entreprise': meta['entreprise'],
                'Pays': meta['pays'],
                'Indice': meta['indice'],
                'Secteur': meta['secteur'],
                'Date': datetime.today().strftime('%Y-%m-%d'),
                'Cours': round(price, 2),
                'RSI': round(rsi, 1),
                'MA_short > MA_long': latest['MA_short'] > latest['MA_long'],
                'Volume boosté': latest['Volume'] > latest['Volume_avg'],
                'Score total': score,
                'Score pondéré': weighted,
                'Ratio gain/risque': rr,
                'Avis': avis,
                'Stop Loss': stop,
                'Objectif 1 (+5%)': tgt1,
                'Objectif 2 (+8%)': tgt2
            })
        except Exception as e:
            logging.error(f"Error processing {ticker}: {e}")
    return pd.DataFrame(rows)

# 8. Envoyer un email avec le fichier Excel en pièce jointe
def send_email(df, guide_df, cfg, env):
    filename = cfg['output_file']
    with pd.ExcelWriter(filename) as writer:
        df.to_excel(writer, sheet_name='Opportunites', index=False)
        guide_df.to_excel(writer, sheet_name='Guide', index=False)

    msg = MIMEMultipart()
    msg['From'] = env['EMAIL_SENDER']
    msg['To']   = env['EMAIL_RECIPIENT']
    msg['Subject'] = cfg['email_subject']

    body = cfg['email_body_detected'] if not df.empty else cfg['email_body_none']
    msg.attach(MIMEText(body, 'plain'))

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(open(filename, 'rb').read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename={filename}')
    msg.attach(part)

    with smtplib.SMTP_SSL(cfg['smtp_server'], cfg['smtp_port']) as server:
        server.login(env['EMAIL_SENDER'], env['EMAIL_PASSWORD'])
        server.send_message(msg)
    logging.info("📬 Email sent successfully.")

# 9. Point d’entrée
def main():
    env       = load_env()
    cfg       = load_config()
    with open(cfg['mapping_file'], 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    # Exemple de tableau-guide (à adapter ou charger depuis un fichier si besoin)
    guide_data = [
        ["Score total (sur 3)", "Nombre de critères simples remplis (RSI, MA, volume)", "≥2 = signal retenu"],
        ["Score pondéré (sur 4)", "Pesée des critères", "≥3 = priorité forte"],
        ["RSI", "Survente (<30) / Surachat (>70)", "<30 = achetez / >70 = prudence"],
        ["Ratio gain/risque", "Objectif / perte potentielle", ">1.5 = bon trade"],
        ["MA_short > MA_long", "Tendance haussière", "True = momentum ok"],
        ["Volume boosté", "Volume > moyenne", "True = intérêt du marché"]
    ]
    guide_df = pd.DataFrame(guide_data, columns=['Colonne','Signification','Interprétation'])

    df_ops = prepare_opportunities(mapping, cfg)
    if not df_ops.empty:
        df_ops.sort_values(by='Score pondéré', ascending=False, inplace=True)
    else:
        logging.info("Aucune opportunité détectée aujourd'hui.")

    send_email(df_ops, guide_df, cfg, env)

if __name__ == '__main__':
    main()

