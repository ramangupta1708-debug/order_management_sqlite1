
const $ = id => document.getElementById(id);
const orderType = $("orderType"), nameInput = $("name"), phoneInput = $("phone"), addressInput = $("address"), tableNumber = $("tableNumber"), itemsBox = $("itemsBox");
function showError(id, msg) { const el = $(id); if (el) el.textContent = msg ? "⚠ " + msg : ""; }
function escapeHtml(v) { return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
if (orderType) orderType.addEventListener("change", () => {
  if ($("tableBox")) $("tableBox").classList.toggle("hidden", orderType.value !== "Dine-In");
  if ($("addressBox")) $("addressBox").style.display = orderType.value === "Delivery" ? "block" : (CURRENT_ROLE === "owner" ? "block" : "none");
});
if (phoneInput) phoneInput.addEventListener("input", () => { phoneInput.value = phoneInput.value.replace(/\D/g, "").slice(0,10); showError("phoneError", ""); });
function addItem() {
  const row = document.createElement("div"); row.className = "item-row";
  row.innerHTML = `<div><label>Item</label><input class="item-name" maxlength="100" placeholder="Item name"></div><div><label>Qty</label><input class="item-qty" type="number" min="1" step="1" value="1"></div><div><label>Price</label><input class="item-price" type="number" min="0" step="0.01" placeholder="0.00"></div><div><label>Subtotal</label><input class="item-subtotal" readonly value="0.00"></div><button type="button" class="danger remove-item">✕</button><small class="error item-error"></small>`;
  itemsBox.appendChild(row); row.querySelectorAll(".item-qty,.item-price").forEach(el=>el.addEventListener("input", updateTotal)); row.querySelector(".remove-item").addEventListener("click",()=>{row.remove();updateTotal();});
}
function updateTotal(){let total=0;document.querySelectorAll(".item-row").forEach(row=>{let q=Number(row.querySelector(".item-qty").value)||0,p=Number(row.querySelector(".item-price").value)||0,s=q*p;row.querySelector(".item-subtotal").value=s.toFixed(2);total+=s;}); if($("totalAmount")) $("totalAmount").textContent=total.toFixed(2);}
if ($("addItem")) $("addItem").addEventListener("click", addItem);
if ($("completeOrder")) $("completeOrder").addEventListener("click", async()=>{
  $("orderMessage").innerHTML="";
  if(!orderType.value){showError("orderTypeError","Select an order type.");return;} showError("orderTypeError","");
  if(!nameInput.value.trim()){showError("nameError","Customer name is required.");return;} showError("nameError","");
  if(CURRENT_ROLE==="owner" && (!phoneInput || !/^\d{10}$/.test(phoneInput.value.trim()))){showError("phoneError","Enter exactly 10 digits.");return;}
  if(CURRENT_ROLE==="owner" && orderType.value==="Delivery" && addressInput && !addressInput.value.trim()){showError("addressError","Address is required for delivery.");return;}
  if(orderType.value==="Dine-In" && (!tableNumber || !Number.isInteger(Number(tableNumber.value)) || Number(tableNumber.value)<=0)){showError("tableError","Enter a valid table number.");return;}
  const rows=[...document.querySelectorAll(".item-row")]; if(!rows.length){$("orderMessage").innerHTML='<div class="error-box">Add at least one item.</div>';return;}
  const items=[]; for(const row of rows){const item_name=row.querySelector(".item-name").value.trim(),quantity=Number(row.querySelector(".item-qty").value),price=Number(row.querySelector(".item-price").value);if(!item_name||!Number.isInteger(quantity)||quantity<=0||!Number.isFinite(price)||price<0){row.querySelector(".item-error").textContent="Check item name, quantity and price.";return;}row.querySelector(".item-error").textContent="";items.push({item_name,quantity,price});}
  const payload={order_type:orderType.value,name:nameInput.value.trim(),phone:CURRENT_ROLE==="owner"?phoneInput.value.trim():null,address:CURRENT_ROLE==="owner"&&addressInput?addressInput.value.trim():null,table_number:orderType.value==="Dine-In"?tableNumber.value:null,items};
  try{const res=await fetch("/api/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const out=await res.json();$("orderMessage").innerHTML=!res.ok||!out.success?`<div class="error-box">⚠ ${escapeHtml(out.message)}</div>`:`<div class="success-box">✓ ${escapeHtml(out.message)}<br>Order ID: #${out.order_id}<br>Total: ₹${Number(out.total).toFixed(2)}</div>`;if(res.ok&&out.success){document.querySelectorAll(".item-row").forEach(r=>r.remove());nameInput.value="";if(phoneInput)phoneInput.value="";if(addressInput)addressInput.value="";if(tableNumber)tableNumber.value="";addItem();updateTotal();}}catch(e){$("orderMessage").innerHTML='<div class="error-box">Server connection error.</div>';}
});
if (CURRENT_ROLE === "owner" && $("searchByDate")) $("searchByDate").addEventListener("click", async()=>{
  const date=$("searchDate").value; $("customerResult").innerHTML="";showError("searchError","");if(!date){showError("searchError","Select a date first.");return;}
  try{const res=await fetch(`/api/orders-by-date/${encodeURIComponent(date)}`);const out=await res.json();if(!res.ok||!out.success){showError("searchError",out.message||"Search failed.");return;}if(!out.orders.length){$("customerResult").innerHTML='<p>No orders found for this date.</p>';return;}
    $("customerResult").innerHTML=out.orders.map(o=>`<div class="customer-box"><h3>Order #${o.order_id}</h3><p><b>Date/time:</b> ${escapeHtml(o.created_at)}<br><b>Customer:</b> ${escapeHtml(o.customer_name||"Staff order")}<br><b>Phone:</b> ${escapeHtml(o.phone||"Not recorded")}<br><b>Address:</b> ${escapeHtml(o.address||"Not recorded")}<br><b>Type:</b> ${escapeHtml(o.order_type)}${o.table_number?`<br><b>Table:</b> ${o.table_number}`:""}<br><b>Status:</b> ${escapeHtml(o.status)}</p><b>Purchased items</b><ul>${o.items.map(i=>`<li>${escapeHtml(i.item_name)} × ${i.quantity} — ₹${Number(i.subtotal).toFixed(2)}</li>`).join("")}</ul><b>Total: ₹${Number(o.total_amount).toFixed(2)}</b></div>`).join("");
  }catch(e){showError("searchError","Server connection error.");}
});
if ($("logout")) $("logout").addEventListener("click",async()=>{await fetch("/logout",{method:"POST"});window.location.href="/login";});
addItem();
