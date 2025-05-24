
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

        score = 0
        score_pondere = 0
        if rsi < 40:
            score += 1
            score_pondere += 1
        if ma5 > ma20:
            score += 1
            score_pondere += 1.5
        if volume > 0.8 * volume_moy:
            score += 1
            score_pondere += 1.5
        if rsi < 30:
            score_pondere += 1  # bonus

        gain_pot = cours * 0.05
        perte = cours * 0.03
        ratio_gr = round(gain_pot / perte, 2)

        if score >= 2:
            if rsi < 30:
                avis = "RSI < 30 ✅"
            elif rsi > 70:
                avis = "RSI > 70 ⚠️"
            else:
                avis = "RSI neutre"
            opportunites.append({
                "Ticker": ticker,
                "Entreprise": mapping[ticker]["entreprise"],
                "Pays": mapping[ticker]["pays"],
                "Indice": mapping[ticker]["indice"],
                "Secteur": mapping[ticker]["secteur"],
                "Date": datetime.today().strftime("%Y-%m-%d"),
                "Cours": round(cours, 2),
                "RSI": round(rsi, 1),
                "MA5 > MA20": ma5 > ma20,
                "Volume boosté": volume > volume_moy,
                "Score total": score,
                "Score pondéré": round(score_pondere, 1),
                "Ratio gain/risque": ratio_gr,
                "Avis": avis,
                "Stop Loss": round(cours * 0.97, 2),
                "Objectif 1 (+5%)": round(cours * 1.05, 2),
                "Objectif 2 (+8%)": round(cours * 1.08, 2)
            })
    except Exception as e:
        print(f"Erreur avec {ticker}: {e}")

# Construction du fichier Excel avec deux onglets
fichier_excel = "opportunites_detectees.xlsx"
guide_data = [
    ["Score total (sur 3)", "Nombre de critères simples remplis (RSI, MA5>MA20, volume)", "≥2 = signal retenu. Plus c’est haut, plus c’est fiable"],
    ["Score pondéré (sur 4)", "Score ajusté : RSI<40 +1, MA5>MA20 +1.5, Volume>0.8×moy +1.5, RSI<30 bonus +1", "≥3 = priorité forte, 2–2.5 = à surveiller, <2 = éviter"],
    ["RSI", "Indicateur de survente (<30) ou surachat (>70)", "<30 = rebond possible ✅ / >70 = prudence ⚠️"],
    ["Ratio gain/risque", "Objectif 1 divisé par perte potentielle (objectif/stop-loss)", ">1.5 = excellent / <1 = mauvaise opportunité"],
    ["MA5 > MA20", "Tendance haussière court/moyen terme", "True = bon momentum 🔼"],
    ["Volume boosté", "Volume actuel supérieur à la moyenne des 10 derniers jours", "True = intérêt du marché 🧠"]
]
df_guide = pd.DataFrame(guide_data, columns=["Colonne", "Signification", "Comment interpréter / Agir"])

if opportunites:
    df_final = pd.DataFrame(opportunites)
    df_final.sort_values(by="Score pondéré", ascending=False, inplace=True)
    message = f"📈 Opportunités détectées : {len(opportunites)}\n\nVoir fichier joint."
else:
    df_final = pd.DataFrame(columns=[
        "Ticker", "Entreprise", "Pays", "Indice", "Secteur",
        "Date", "Cours", "RSI", "MA5 > MA20", "Volume boosté",
        "Score total", "Score pondéré", "Ratio gain/risque", "Avis",
        "Stop Loss", "Objectif 1 (+5%)", "Objectif 2 (+8%)"
    ])
    message = "📭 Aucune opportunité détectée aujourd’hui. Voir fichier joint."

with pd.ExcelWriter(fichier_excel) as writer:
    df_final.to_excel(writer, sheet_name="Opportunites", index=False)
    df_guide.to_excel(writer, sheet_name="Guide_Priorisation", index=False)

# Envoi du mail
msg = MIMEMultipart()
msg["From"] = EMAIL_EXPEDITEUR
msg["To"] = EMAIL_DESTINATAIRE
msg["Subject"] = "📢 Résultat analyse de trading court terme"
msg.attach(MIMEText(message, "plain"))

with open(fichier_excel, "rb") as f:
    part = MIMEBase("application", "octet-stream")
    part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={fichier_excel}")
    msg.attach(part)

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_EXPEDITEUR, EMAIL_MDP)
        server.send_message(msg)
    print("📬 Email envoyé avec succès.")
except Exception as e:
    print(f"❌ Erreur lors de l’envoi de l’e-mail : {e}")
