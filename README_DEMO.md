# GrameenAI Advisor Demo Guide

## Local Run Commands
To run the full application locally, you will need two terminal tabs.

### 1. Start the Backend
```bash
# Navigate to the backend directory
cd backend

# Activate your virtual environment (if using one)
# e.g., source .venv/bin/activate or .venv\Scripts\activate

# Run the FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the Frontend
```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies (only needed the first time)
npm install

# Start the Next.js development server
npm run dev
```
Open `http://localhost:3000/research` in your browser to view the demo.

---

## Sample Inputs (Pre-tested)
For the best live demonstration experience, copy and paste one of these sample inputs into the search bar:

1. **"Vegetable seller in rural Maharashtra, earning ₹15k/month"**
2. **"Tailor in tier-2 city, ₹25k/month, needs sewing machine loan"**
3. **"Small dairy farmer in Gujarat, 3 cows, ₹20k/month"**

*Note: If the application hits OpenRouter API rate limits, the UI will gracefully degrade to a clear fallback state requesting a retry, preventing any application crashes.*

---

## Competitive Positioning

| Feature / Target Audience | Existing MSME-AI Tools (e.g. msmeindia.ai, YojanaRadar, TenderKart) | GrameenAI Advisor (This Prototype) |
|---------------------------|----------------------------------------------------------------------|------------------------------------|
| **Target Audience** | Formal, GST-registered businesses, already somewhat digitized. | Informal, cash-only, pre-Udyam micro-entrepreneurs. |
| **User Inputs** | Complex forms, structured financial data, PAN/GST numbers. | Plain-language, conversational input. |
| **Output / Value Add** | Scheme matching, tender bidding, advanced compliance dashboards. | Produces a structured "Loan Readiness Advisory" profile, generating the *input* formal tools need. |
| **Assumed Literacy** | English, high dashboard and financial literacy. | Basic literacy, non-jargon. Designed for eventual vernacular voice & WhatsApp integration. |
| **Position in Ecosystem** | End-of-funnel fulfillment for established MSMEs. | Top-of-funnel onboarding for the unbanked/informal sector to bridge them into the formal economy. |

*Takeaway: We are not competing with existing platforms—we are creating the on-ramp for the millions of informal micro-entrepreneurs they currently cannot serve.*

---

## Roadmap Note: Voice and WhatsApp
Voice input (ASR/TTS) and WhatsApp chatbot functionality are **Phase 2 roadmap features**. 
At the bottom of the main dashboard UI (`/research`), you will find a dedicated "Coming in Phase 2" panel containing visual mockups of these planned features. These elements are currently UI-only mockups to illustrate the long-term vernacular and accessibility vision.
