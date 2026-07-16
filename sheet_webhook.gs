// Paste into Extensions > Apps Script of the tracking Google Sheet, then
// Deploy > New deployment > Web app, Execute as: Me, Access: Anyone.
// The /exec URL goes into the repo's SHEET_WEBHOOK_URL Actions secret.

const HEADER = ["Date", "Ticker", "Score", "Entry $", "Current $", "P/L %",
                "SPY @ entry", "SPY now", "vs SPY", "Analyst target",
                "Upside % @ pick", "Claude's verdict"];

function doPost(e) {
  const sheet = SpreadsheetApp.openById("1A5-jj4FTdN1VMwkxj_iTuJlhQ7QUUW1HrL3RbROcDis").getSheets()[0];
  if (sheet.getLastRow() === 0) sheet.appendRow(HEADER);
  const rows = JSON.parse(e.postData.contents).rows;
  rows.forEach(function (p) {
    sheet.appendRow([p.date, p.ticker, p.score, p.entry_price, "", "",
                     p.spy_entry, "", "", p.analyst_target, p.upside_pct,
                     p.verdict]);
    const r = sheet.getLastRow();
    sheet.getRange(r, 5).setFormula('=GOOGLEFINANCE(B' + r + ',"price")');
    sheet.getRange(r, 6).setFormula('=IFERROR(E' + r + '/D' + r + '-1,"")')
         .setNumberFormat("+0.0%;-0.0%");
    sheet.getRange(r, 8).setFormula('=GOOGLEFINANCE("SPY","price")');
    sheet.getRange(r, 9).setFormula('=IFERROR(F' + r + '-(H' + r + '/G' + r + '-1),"")')
         .setNumberFormat("+0.0%;-0.0%");
  });
  return ContentService.createTextOutput("ok");
}
