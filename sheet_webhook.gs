// Paste into Extensions > Apps Script of the tracking Google Sheet, then
// Deploy > New deployment > Web app, Execute as: Me, Access: Anyone.
// The /exec URL goes into the repo's SHEET_WEBHOOK_URL Actions secret.

const HEADER = ["Date", "Ticker", "Score", "Entry $", "Current $", "P/L %",
                "SPY @ entry", "SPY now", "vs SPY", "Analyst target",
                "Upside % @ pick", "Claude's verdict"];

const SHEET_ID = "1A5-jj4FTdN1VMwkxj_iTuJlhQ7QUUW1HrL3RbROcDis";

// Run this ONCE from the Apps Script editor (select installTrigger, press Run).
// Standalone script, so a simple onOpen never fires — this installs a real
// on-open trigger pointed at the sheet.
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "refreshPrices") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("refreshPrices").forSpreadsheet(SHEET_ID).onOpen().create();
}

// Blanks then rewrites the GOOGLEFINANCE cells (cols E and H) so Sheets is
// forced to refetch prices every time the sheet is opened.
function refreshPrices() {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
  const last = sheet.getLastRow();
  if (last < 2) return;
  sheet.getRange(2, 5, last - 1).clearContent();  // Current $
  sheet.getRange(2, 8, last - 1).clearContent();  // SPY now
  SpreadsheetApp.flush();
  for (let r = 2; r <= last; r++) {
    sheet.getRange(r, 5).setFormula('=GOOGLEFINANCE(B' + r + ',"price")');
    sheet.getRange(r, 8).setFormula('=GOOGLEFINANCE("SPY","price")');
  }
}

function doPost(e) {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
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
