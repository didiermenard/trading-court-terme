import os
import smtplib
import yfinance as yf
import json
import pandas as pd
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Charger les variables d’environnement
load_dotenv()
EMAIL_EXPEDITEUR = os.getenv("EMAIL_EXPEDITEUR")
EMAIL_MDP = os.getenv("EMAIL_MDP")
EMAIL_DESTINATAIRE = os.getenv("EMAIL_DESTINATAIRE")

# Charger le mapping depuis le fichier JSON
with open("ticker_entreprise_mapping.json", "r", encoding="utf-8") as f:
    mapping_ticker_nom = json.load(f)

# Paramètres
duree_moyenne = 20
tickers = list(mapping_ticker_nom.keys())

# Résultats
opportunites = []

for ticker in tickers:
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)

        if df.empty or len(df) < duree_moyenne:
            continue

        df["MA5"] = df["Close"].rolling(window=5).mean()
        df["MA20"] = df["Close"].rolling(window=20).mean()
        df["RSI"] = 100 - (100 / (1 + df["Close"].pct_change().add(1).rolling(14).apply(lambda x: (x[x > 0].mean() / abs(x[x < 0].mean())) if not x[x < 0].empty else 0)))

        dernier = df.iloc[-1]
        vol_moy = df["Volume"].rolling(window=20).mean().iloc[-1]
        conditions = (
            dernier["RSI"] < 30
            and dernier["MA5"] > dernier["MA20"]
            and dernier["Volume"] > vol_moy
        )

        if conditions:
            cours = round(dernier["Close"], 2)
            stop_loss = round(cours * 0.97, 2)
            objectif_1 = round(cours * 1.05, 2)
            objectif_2 = round(cours * 1.08, 2)

            opportunites.append({
                "Ticker": ticker,
                "Entreprise": mapping_ticker_nom[ticker],
                "Date": df.index[-1].strftime("%Y-%m-%d"),
                "Cours": cours,
                "RSI": round(dernier["RSI"], 1),
                "MA5 > MA20": True,
                "Volume boosté": True,
                "Stop Loss": stop_loss,
                "Objectif 1 (+5%)": objectif_1,
                "Objectif 2 (+8%)": objectif_2
            })
    except Exception as e:
        print(f"⚠️ Erreur sur {ticker} : {e}")

# Sauvegarde Excel
if opportunites:
    df_opps = pd.DataFrame(opportunites)
    df_opps.to_excel("opportunites_detectees.xlsx", index=False)

    # Corps du message
    texte = "\n".join(
        [f"{o['Entreprise']} ({o['Ticker']}) — cours {o['Cours']} €" for o in opportunites]
    )
    msg = MIMEText("🚀 Opportunités détectées :\n\n" + texte)
    msg["Subject"] = "📈 Opportunités de trading détectées"
    msg["From"] = EMAIL_EXPEDITEUR
    msg["To"] = EMAIL_DESTINATAIRE

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_EXPEDITEUR, EMAIL_MDP)
            server.send_message(msg)
        print("✅ Email envoyé avec succès.")
    except Exception as e:
        print(f"❌ Erreur d'envoi : {e}")
else:
    print("📭 Aucune opportunité détectée aujourd'hui.")
