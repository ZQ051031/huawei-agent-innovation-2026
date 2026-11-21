"use strict";
const $ = id => document.getElementById(id);
const translations = {
  en: {
    local:"LOCAL WORKSPACE",eyebrow:"01 / FINANCE WORKSPACE",title:"Know where your money went.",
    intro:"Turn receipts and bank exports into a ledger that answers back.",demo:"Load demo data",dashboard:"Monthly overview",
    month:"Month",spending:"Spending by category",review:"Needs review",agentTag:"02 / AGENT DESK",agent:"Ask ClearBooks",
    question:"Question",ask:"Ask",importTag:"03 / DOCUMENT INBOX",inbox:"Import documents",uploadLabel:"TXT, CSV or text PDF · max 5 MB each",
    upload:"Import files",paste:"Or paste document text",saveText:"Import pasted text",budgets:"Budgets",category:"Category",
    currency:"Currency",limit:"Limit",saveBudget:"Save budget",report:"Monthly report",
    reportDesc:"Generate a plain-language review for the selected month.",generate:"Generate report",ledger:"Ledger and sources",
    date:"Date",vendor:"Vendor",amount:"Amount",source:"Source",footer:"Local by default · review before filing",
    income:"Income",expense:"Expenses",net:"Net cash flow",noSpending:"No spending for this month.",noAlerts:"No expenses flagged this month.",
    noBudget:"No budgets set for this month.",noRows:"No transactions for this month.",evidence:"Source excerpts",
    saved:"Budget saved.",optional:"Optional AI note",pending:"Working…",large:"Large",unusual:"Unusual",large_and_unusual:"Large and unusual",
    examples:["Office supplies in November?","Which vendor did I pay most?","Find document: Net 30"],
    names:{office:"Office supplies",software:"Software",travel:"Travel",meals:"Meals",equipment:"Equipment",utilities:"Utilities",other:"Other"}
  },
  zh: {
    local:"本地工作区",eyebrow:"01 / 财务工作区",title:"你的钱都花在哪？",intro:"将收据和银行流水变成可问答的账本。",demo:"载入演示数据",
    dashboard:"月度总览",month:"月份",spending:"分类支出",review:"待人工复核",agentTag:"02 / 智能体工作台",agent:"问问 ClearBooks",
    question:"问题",ask:"提问",importTag:"03 / 文档收件箱",inbox:"导入文档",uploadLabel:"TXT、CSV、文字版 PDF · 每个最大 5 MB",
    upload:"导入文件",paste:"或粘贴文档文字",saveText:"导入文本",budgets:"预算",category:"类别",currency:"币种",limit:"限额",
    saveBudget:"保存预算",report:"月度报告",reportDesc:"生成所选月份的通俗财务报告。",generate:"生成报告",ledger:"账本与来源",
    date:"日期",vendor:"商户",amount:"金额",source:"来源",footer:"默认本地处理 · 入账前请人工核对",
    income:"收入",expense:"支出",net:"净现金流",noSpending:"本月无支出。",noAlerts:"本月无待复核支出。",noBudget:"本月未设置预算。",
    noRows:"本月无交易。",evidence:"来源摘录",saved:"预算已保存。",optional:"可选 AI 说明",pending:"处理中…",
    large:"大额",unusual:"异常",large_and_unusual:"大额且异常",
    examples:["11月办公用品花了多少？","哪家供应商付款最多？","查找文档：Net 30"],
    names:{office:"办公用品",software:"软件服务",travel:"差旅",meals:"餐饮",equipment:"设备",utilities:"公用事业",other:"其他"}
  }
};
let lang = localStorage.getItem("clearbooks-language") === "zh" ? "zh" : "en";
let snapshot;
let generation = 0;
const words = () => translations[lang];
const figure = cents => (cents / 100).toLocaleString("en-US", {minimumFractionDigits:2, maximumFractionDigits:2});
const cash = (code, cents) => code + " " + figure(cents);
const add = (parent, tag, value, style) => {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (style) node.className = style;
  parent.append(node);
  return node;
};
function line(parent, label, value, warning = false) {
  const row = add(parent, "div", undefined, "row" + (warning ? " warning" : ""));
  add(row, "span", label); add(row, "span", value);
}
function status(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("warning", error);
  $("status").hidden = !text;
}
async function api(path, data) {
  const response = await fetch("/api/" + path, data === undefined ? undefined : {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)
  });
  const body = await response.json();
  if (!response.ok) throw Error(body.error || response.statusText);
  return body;
}
async function refresh(month) {
  const id = ++generation;
  const value = await api("summary" + (month ? "?month=" + encodeURIComponent(month) : ""));
  if (id !== generation) return;
  snapshot = value;
  $("month").value = snapshot.month;
  render();
}
function option(select, value, label) {
  const n = add(select, "option", label);
  n.value = value;
}
function language() {
  const t = words();
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  $("language").textContent = lang === "zh" ? "English" : "中文";
  document.querySelectorAll("[data-copy]").forEach(node => node.textContent = t[node.dataset.copy]);
  $("question").placeholder = t.examples[1];
  $("text").placeholder = lang === "zh" ? "商户：…" : "Vendor: …";
  $("examples").replaceChildren();
  for (const text of t.examples) {
    const b = add($("examples"), "button", text);
    b.type = "button";
    b.addEventListener("click", () => { $("question").value = text; $("question").focus(); });
  }
  const category = $("budget-category"), selected = category.value || "office";
  category.replaceChildren();
  Object.entries(t.names).forEach(([key, label]) => option(category, key, label));
  category.value = selected;
  if (snapshot) render();
}
function render() {
  const t = words(), s = snapshot;
  for (const id of ["totals","categories","alerts","budgets","ledger"]) $(id).replaceChildren();
  const currencies = Object.entries(s.currencies).sort(([a],[b]) => a.localeCompare(b));
  for (const key of ["income","expense","net"]) {
    const metric = add($("totals"), "div", undefined, "metric");
    add(metric,"h3",t[key]);
    if (!currencies.length) add(metric,"p","—","figure");
    for (const [code, value] of currencies) {
      const row = add(metric,"p",undefined,"figure");
      add(row,"span",figure(value[key]));
      add(row,"small",code);
    }
  }
  let categoryCount = 0;
  for (const [code, group] of currencies) {
    for (const [key, value] of Object.entries(group.categories).sort((a,b) => b[1]-a[1])) {
      categoryCount++;
      line($("categories"),t.names[key],cash(code, value));
      const bar = add($("categories"),"progress",undefined,"bar");
      bar.max = group.expense;
      bar.value = value;
      bar.setAttribute("aria-label", t.names[key] + " · " + cash(code, value));
    }
  }
  if (!categoryCount) add($("categories"),"p",t.noSpending);
  if (!s.alerts.length) add($("alerts"),"p",t.noAlerts);
  for (const a of s.alerts) {
    const item = add($("alerts"),"div",undefined,"alert-item");
    line(item,a.vendor,cash(a.currency,a.cents),true);
    add(item,"p",t[a.reason] + " · " + a.source,"caption");
  }
  if (!s.budgets.length) add($("budgets"),"p",t.noBudget);
  for (const b of s.budgets) {
    line($("budgets"),t.names[b.category],cash(b.currency,b.spent) + " / " + figure(b.cents),b.remaining < 0);
  }
  $("record-count").textContent = lang === "zh" ? s.entries.length + " 笔交易 · " + s.evidence_only + " 条仅供检索"
                                                : s.entries.length + " transactions · " + s.evidence_only + " evidence-only";
  if (!s.entries.length) {
    const row = add($("ledger"),"tr");
    add(row,"td",t.noRows).colSpan = 5;
  }
  for (const r of s.entries) {
    const row = add($("ledger"),"tr");
    [r.date,r.vendor,t.names[r.category]].forEach(value => add(row,"td",value));
    add(row,"td",(r.direction === "expense" ? "−" : "+") + cash(r.currency,r.cents),"money");
    add(row,"td",r.source);
  }
}
function importStatus(rows) {
  return rows.map(r => lang === "zh" ?
    r.source + (r.duplicate_file ? "：文件重复" : "：新增 " + r.added + " / 重复 " + r.duplicates + " / 仅文档 " + r.evidence_only) :
    r.source + (r.duplicate_file ? ": duplicate file" : ": " + r.added + " added / " + r.duplicates + " duplicate / " + r.evidence_only + " evidence-only")
  ).join(" · ");
}
function run(button, work) {
  button.addEventListener(button.closest("form") ? "submit" : "click", async event => {
    event.preventDefault();
    const control = button.matches("form") ? button.querySelector("button") : button;
    control.disabled = true;
    status(words().pending);
    try { await work(); }
    catch (err) { status(err.message, true); }
    finally { control.disabled = false; }
  });
}
async function importUpload(file) {
  if (file.size > 5_000_000) throw Error(file.name + " exceeds 5 MB.");
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  return api("import", {name:file.name,data});
}
function show(id, build) {
  const node = $(id);
  node.replaceChildren();
  node.hidden = false;
  build(node);
}
function clearOutputs() {
  for (const id of ["answer","report-output"]) $(id).hidden = true;
}
$("language").addEventListener("click", () => {
  lang = lang === "en" ? "zh" : "en";
  localStorage.setItem("clearbooks-language",lang);
  clearOutputs(); status(""); language();
});
for (const code of ["CNY","USD","EUR","GBP","HKD","JPY","CAD","AUD","SGD"]) option($("budget-currency"),code,code);
$("month").addEventListener("change", () => {
  if ($("month").validity.valid) { clearOutputs(); refresh($("month").value).catch(err => status(err.message,true)); }
});
run($("demo"), async () => {
  const result = await api("demo",{});
  await refresh("2026-11"); clearOutputs(); status(importStatus(result.imports));
});
run($("upload"), async () => {
  const rows = [], errors = [];
  for (const file of $("file").files) {
    try { rows.push(await importUpload(file)); }
    catch (err) { errors.push(file.name + ": " + (err.message || "Could not read file.")); }
  }
  $("upload").reset();
  await refresh(); clearOutputs(); status([importStatus(rows),...errors].filter(Boolean).join(" · "),Boolean(errors.length));
});
run($("paste"), async () => {
  const result = await api("import",{text:$("text").value});
  $("paste").reset();
  await refresh(); clearOutputs(); status(importStatus([result]));
});
run($("budget"), async () => {
  await api("budget",{month:$("month").value,category:$("budget-category").value,
    currency:$("budget-currency").value,amount:$("budget-amount").value});
  await refresh($("month").value); clearOutputs(); status(words().saved);
});
run($("ask"), async () => {
  const result = await api("ask",{question:$("question").value,month:$("month").value,lang});
  show("answer", node => {
    add(node,"div",[result.intent,...result.trace].map(x=>x.replaceAll("_"," ")).join(" → "),"trace");
    add(node,"p",result.answer);
    if (result.citations.length) {
      const details = add(node,"details");
      details.open = true;
      add(details,"summary",words().evidence);
      const list = add(details,"ol");
      for (const cite of result.citations) {
        const item = add(list,"li",cite.source + (cite.date ? " · " + cite.date : ""));
        add(item,"p",cite.excerpt,"caption");
      }
    }
  }); status("");
});
run($("report"), async () => {
  const result = await api("report",{month:$("month").value,lang});
  show("report-output", node => {
    add(node,"p",result.report);
    if (result.note) { add(node,"h3",words().optional); add(node,"p",result.note); }
  }); status(result.notice || "");
});
language();
refresh().catch(err => status(err.message,true));
