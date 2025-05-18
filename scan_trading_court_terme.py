import os
import json
import smtplib
import yfinance as yf
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()
EMAIL_EXPEDITEUR = os.getenv("EMAIL_EXPEDITEUR")
EMAIL_MDP = os.getenv("EMAIL_MDP")
EMAIL_DESTINATAIRE = os.getenv("EMAIL_DESTINATAIRE")

# Chargement du fichier JSON enrichi
with open("ticker_entreprise_mapping.json", "r", encoding="utf-8") as f:
    mapping = json.load(f)

# Liste des tickers
tickers = list(mapping.keys())
opportunites = []

for ticker in tickers:
    try:
        df = yf.download(ticker, period="3mo", interval="1d", auto_adjust=True, progress=False)

        if df.empty or len(df) < 20:
            continue

        df["MA5"] = df["Close"].rolling(window=5).mean()
        df["MA20"] = df["Close"].rolling(window=20).mean()
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df["RSI"] = 100 - (100 / (1 + rs))
        df["Volume_moy_10j"] = df["Volume"].rolling(window=10).mean()

        dernier = df.dropna().iloc[-1]
        rsi = float(dernier["RSI"])
        ma5 = float(dernier["MA5"])
        ma20 = float(dernier["MA20"])
        volume = float(dernier["Volume"])
        volume_moy = float(dernier["Volume_moy_10j"])
        cours = float(dernier["Close"])

        if rsi < 30 and ma5 > ma20 and volume > volume_moy:
            opportunites.append({
                "Ticker": ticker,
                "Entreprise": mapping[ticker]["entreprise"],
                "Pays": mapping[ticker]["pays"],
                "Indice": mapping[ticker]["indice"],
                "Secteur": mapping[ticker]["secteur"],
                "Date": datetime.today().strftime("%Y-%m-%d"),
                "Cours": round(cours, 2),
                "RSI": round(rsi, 1),
                "MA5 > MA20": True,
                "Volume boosté": True,
                "Stop Loss": round(cours * 0.97, 2),
                "Objectif 1 (+5%)": round(cours * 1.05, 2),
                "Objectif 2 (+8%)": round(cours * 1.08, 2)
            })
    except Exception as e:
        print(f"Erreur avec {ticker}: {e}")

# Préparation du fichier Excel à envoyer
fichier_excel = "opportunites_detectees.xlsx"
if opportunites:
    df_final = pd.DataFrame(opportunites)
    message = f"📈 Opportunités détectées : {len(opportunites)}\n\nVoir pièce jointe."
else:
    message = "📭 Aucune opportunité détectée aujourd’hui."
    df_final = pd.DataFrame(columns=[
        "Ticker", "Entreprise", "Pays", "Indice", "Secteur",
        "Date", "Cours", "RSI", "MA5 > MA20", "Volume boosté",
        "Stop Loss", "Objectif 1 (+5%)", "Objectif 2 (+8%)"
    ])

df_final.to_excel(fichier_excel, index=False)

# Préparation de l’e-mail
msg = MIMEMultipart()
msg["From"] = EMAIL_EXPEDITEUR
msg["To"] = EMAIL_DESTINATAIRE
msg["Subject"] = "📢 Résultat analyse de trading court terme"

msg.attach(MIMEText(message, "plain"))

# Pièce jointe
with open(fichier_excel, "rb") as f:
    part = MIMEBase("application", "octet-stream")
    part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={fichier_excel}")
    msg.attach(part)

# Envoi de l’e-mail
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_EXPEDITEUR, EMAIL_MDP)
        server.send_message(msg)
    print("📬 Email envoyé avec succès.")
except Exception as e:
    print(f"❌ Erreur lors de l’envoi de l’email : {e}")
