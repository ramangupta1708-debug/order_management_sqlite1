const $ = id => document.getElementById(id);
const orderType = $('orderType'), nameInput = $('name'), phoneInput = $('phone'), addressInput = $('address'), tableNumber = $('tableNumber'), itemsBox = $('itemsBox');
function showError(id, msg) { const el = $(id); if (el) el.textContent = msg ? '⚠ ' + msg : ''; }
function escapeHtml(v) { return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;'); }
async function api(url, options={}) {
  const res = await fetch(url, { headers: {'Content-Type':'application/json', ...(options.headers||{})}, ...options });
  let data; try { data = await res.json(); } catch { data = {success:false,message:'Unexpected server response.'}; }
  if (!res.ok || data.success === false) throw new Error(data.message || `Request failed (${res.status})`);
  return data;
}
function syncOrderType() {
  if ($('tableBox')) $('tableBox').classList.toggle('hidden', orderType.value !== 'Dine-In');
  if ($('addressBox')) $('addressBox').style.display = 'block';
  if (tableNumber) tableNumber.required = orderType.value === 'Dine-In';
  if (addressInput) addressInput.required = orderType.value === 'Delivery';
}
if (orderType) { orderType.addEventListener('change', syncOrderType); syncOrderType(); }
if (phoneInput) phoneInput.addEventListener('input', () => { phoneInput.value = phoneInput.value.replace(/\D/g,'').slice(0,10); showError('phoneError',''); });
function addItem(item={}) {
  const row=document.createElement('div'); row.className='item-row';
  row.innerHTML=`<div><label>Item</label><input class="item-name" maxlength="100" placeholder="Item name" value="${escapeHtml(item.item_name||'')}"></div><div><label>Qty</label><input class="item-qty" type="number" min="1" step="1" value="${Number(item.quantity)||1}"></div><div><label>Price</label><input class="item-price" type="number" min="0" step="0.01" placeholder="0.00" value="${item.price!==undefined?Number(item.price):''}"></div><div><label>Subtotal</label><input class="item-subtotal" readonly value="0.00"></div><button type="button" class="danger remove-item" aria-label="Remove item">✕</button><small class="error item-error"></small>`;
  itemsBox.appendChild(row); row.querySelectorAll('.item-qty,.item-price').forEach(el=>el.addEventListener('input',updateTotal)); row.querySelector('.remove-item').addEventListener('click',()=>{row.remove();updateTotal();}); updateTotal();
}
function updateTotal(){let total=0;document.querySelectorAll('.item-row').forEach(row=>{const q=Number(row.querySelector('.item-qty').value)||0,p=Number(row.querySelector('.item-price').value)||0,s=q*p;row.querySelector('.item-subtotal').value=s.toFixed(2);total+=s;});if($('totalAmount'))$('totalAmount').textContent=total.toFixed(2);}
if ($('addItem')) $('addItem').addEventListener('click',()=>addItem());
function readItems(){
  const rows=[...document.querySelectorAll('.item-row')]; if(!rows.length) throw new Error('Add at least one item.');
  return rows.map(row=>{const item_name=row.querySelector('.item-name').value.trim(),quantity=Number(row.querySelector('.item-qty').value),price=Number(row.querySelector('.item-price').value);if(!item_name||!Number.isInteger(quantity)||quantity<=0||!Number.isFinite(price)||price<0)throw new Error('Check every item name, quantity and price.');return {item_name,quantity,price};});
}
function orderPayload(orderStatus='Pending'){
  if(!orderType.value)throw new Error('Select an order type.');
  if(!nameInput.value.trim())throw new Error('Customer name is required.');
  if(phoneInput.value.trim() && !/^\d{10}$/.test(phoneInput.value.trim()))throw new Error('Phone number must contain exactly 10 digits, or leave it blank.');
  if(orderType.value==='Delivery'&&!addressInput.value.trim())throw new Error('Address is required for delivery.');
  if(orderType.value==='Dine-In'&&(!Number.isInteger(Number(tableNumber.value))||Number(tableNumber.value)<=0))throw new Error('Enter a valid table number.');
  if(!$('paymentMethod').value)throw new Error('Select a payment method.');
  return {order_type:orderType.value,name:nameInput.value.trim(),phone:phoneInput.value.trim(),address:addressInput.value.trim(),table_number:orderType.value==='Dine-In'?tableNumber.value:null,items:readItems(),payment_method:$('paymentMethod').value,payment_status:$('paymentStatus').value,status:orderStatus};
}
let chosenOrderStatus = 'Pending';
document.querySelectorAll('.order-submit').forEach(button => button.addEventListener('click', () => { chosenOrderStatus = button.dataset.orderStatus || 'Pending'; }));
if ($('orderForm')) $('orderForm').addEventListener('submit',async e=>{
  e.preventDefault();
  const submitter = e.submitter;
  const orderStatus = submitter?.dataset?.orderStatus || chosenOrderStatus || 'Pending';
  const message=$('orderMessage'); message.innerHTML='';
  try{
    const payload=orderPayload(orderStatus);
    const out=await api('/api/orders',{method:'POST',body:JSON.stringify(payload)});
    const statusLabel = orderStatus === 'Cancelled' ? 'Cancelled' : orderStatus;
    message.innerHTML=`<div class="success-box">✓ Order saved as <b>${escapeHtml(statusLabel)}</b>.<br>Order ID: #${out.order_id}<br>Bill total: ₹${Number(out.total).toFixed(2)}<br>Payment: ${escapeHtml(payload.payment_method)} / ${escapeHtml(payload.payment_status)}</div>`;
    nameInput.value='';phoneInput.value='';addressInput.value='';tableNumber.value='';orderType.value='';$('paymentMethod').value='';$('paymentStatus').value='Pending';itemsBox.innerHTML='';addItem();syncOrderType();
    await loadOrders();
  }catch(err){message.innerHTML=`<div class="error-box">⚠ ${escapeHtml(err.message)}</div>`;}
});
function renderItems(items){return `<ul>${(items||[]).map(i=>`<li>${escapeHtml(i.item_name)} × ${Number(i.quantity)} — ₹${Number(i.subtotal).toFixed(2)}</li>`).join('')}</ul>`;}
function renderManagedOrder(o){
  const statuses=['Pending','Confirmed','Preparing','Ready','Completed','Cancelled','New'];
  return `<div class="customer-box" data-order-id="${Number(o.order_id)}"><h3>Order #${Number(o.order_id)} — ${escapeHtml(o.customer_name||'Customer')}</h3><p><b>Time:</b> ${escapeHtml(o.created_at)}<br><b>Type:</b> ${escapeHtml(o.order_type)}${o.table_number?`<br><b>Table:</b> ${Number(o.table_number)}`:''}<br><b>Order status:</b> ${escapeHtml(o.status)}<br><b>Payment:</b> ${escapeHtml(o.payment_method||'Cash')} / ${escapeHtml(o.payment_status||'Paid')}<br><b>Total:</b> ₹${Number(o.total_amount).toFixed(2)}</p><b>Items</b>${renderItems(o.items)}<div class="manage-actions"><label>Order status<select class="status-select">${statuses.map(s=>`<option ${s===o.status?'selected':''}>${s}</option>`).join('')}</select></label><label>Payment status<select class="payment-status-select"><option ${o.payment_status==='Pending'?'selected':''}>Pending</option><option ${o.payment_status==='Paid'?'selected':''}>Paid</option></select></label><button type="button" class="primary save-status">Save status</button><button type="button" class="secondary edit-order">Edit order</button><button type="button" class="danger delete-order">Delete order</button><small class="error action-error"></small></div></div>`;
}
let activeStatusFilter = 'All';
async function loadOrders(){
  showError('manageOrdersError','');$('ordersList').innerHTML='';
  const params = new URLSearchParams();
  params.set('status', activeStatusFilter);
  params.set('payment', $('managePaymentFilter')?.value || 'All');
  params.set('search', $('manageSearch')?.value.trim() || '');
  if ($('manageOrderDate')?.value) params.set('date', $('manageOrderDate').value);
  try{
    const out=await api(`/api/manage-orders?${params.toString()}`);
    if(!out.orders.length){$('ordersList').innerHTML='<p>No orders match these filters.</p>';return;}
    $('ordersList').innerHTML=out.orders.map(renderManagedOrder).join('');
  }catch(e){showError('manageOrdersError',e.message);}
}
if($('loadOrders'))$('loadOrders').addEventListener('click',loadOrders);
if($('statusFilters')) $('statusFilters').addEventListener('click', e => {
  const button=e.target.closest('[data-status]'); if(!button)return;
  activeStatusFilter=button.dataset.status;
  document.querySelectorAll('.filter-button').forEach(b=>{b.classList.toggle('active',b===button);b.classList.toggle('primary',b===button);b.classList.toggle('secondary',b!==button);});
  loadOrders();
});
if($('managePaymentFilter')) $('managePaymentFilter').addEventListener('change',loadOrders);
if($('manageSearch')) $('manageSearch').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();loadOrders();}});
if($('ordersList'))$('ordersList').addEventListener('click',async e=>{
  const card=e.target.closest('[data-order-id]');if(!card)return;const id=card.dataset.orderId;const err=card.querySelector('.action-error');err.textContent='';
  try{
    if(e.target.classList.contains('save-status')){await api(`/api/orders/${id}`,{method:'PUT',body:JSON.stringify({status:card.querySelector('.status-select').value,payment_status:card.querySelector('.payment-status-select').value})});await loadOrders();return;}
    if(e.target.classList.contains('delete-order')){if(!confirm(`Delete order #${id}? This cannot be undone.`))return;await api(`/api/orders/${id}`,{method:'DELETE'});await loadOrders();return;}
    if(e.target.classList.contains('edit-order')){
      const newName=prompt('Customer name (leave unchanged by pressing Cancel):');if(newName===null)return;
      const newType=prompt('Order type: Dine-In, Delivery, or Packing', 'Packing');if(newType===null)return;
      const normalized={'dine-in':'Dine-In','delivery':'Delivery','packing':'Packing'}[newType.trim().toLowerCase()];if(!normalized)throw new Error('Order type must be Dine-In, Delivery, or Packing.');
      const table=normalized==='Dine-In'?prompt('Table number:','1'):null; if(normalized==='Dine-In'&&table===null)return;
      const address=normalized==='Delivery'?prompt('Delivery address:',''):'';if(normalized==='Delivery'&&address===null)return;
      const phone=prompt('Customer phone (10 digits, or blank):','');if(phone===null)return;
      const payment_method=prompt('Payment method: Cash or Online','Cash');if(payment_method===null)return;
      const itemsText=prompt('Enter items as Name,Qty,Price separated by semicolons. Example: Tea,2,20; Sandwich,1,80','');if(itemsText===null)return;
      const items=itemsText.split(';').map(part=>{const [item_name,qty,price]=part.split(',');return {item_name:(item_name||'').trim(),quantity:Number(qty),price:Number(price)};});
      await api(`/api/orders/${id}/edit`,{method:'PUT',body:JSON.stringify({name:newName.trim(),order_type:normalized,table_number:table,phone:phone.trim(),address:(address||'').trim(),payment_method:payment_method.trim(),items})});await loadOrders();
    }
  }catch(ex){err.textContent='⚠ '+ex.message;}
});
if (CURRENT_ROLE==='owner' && $('searchByDate')) $('searchByDate').addEventListener('click',async()=>{
  const date=$('searchDate').value;$('customerResult').innerHTML='';showError('searchError','');if(!date){showError('searchError','Select a date first.');return;}
  try{const out=await api(`/api/orders-by-date/${encodeURIComponent(date)}`);if(!out.orders.length){$('customerResult').innerHTML='<p>No orders found for this date.</p>';return;}
    $('customerResult').innerHTML=out.orders.map(o=>`<div class="customer-box"><h3>Order #${Number(o.order_id)}</h3><p><b>Date/time:</b> ${escapeHtml(o.created_at)}<br><b>Customer:</b> ${escapeHtml(o.customer_name||'Not recorded')}<br><b>Phone:</b> ${escapeHtml(o.phone||'Not recorded')}<br><b>Address:</b> ${escapeHtml(o.address||'Not recorded')}<br><b>Type:</b> ${escapeHtml(o.order_type)}${o.table_number?`<br><b>Table:</b> ${Number(o.table_number)}`:''}<br><b>Status:</b> ${escapeHtml(o.status)}<br><b>Payment:</b> ${escapeHtml(o.payment_method||'Cash')} / ${escapeHtml(o.payment_status||'Paid')}</p><b>Purchased items</b>${renderItems(o.items)}<b>Total: ₹${Number(o.total_amount).toFixed(2)}</b></div>`).join('');
  }catch(e){showError('searchError',e.message);}
});
if ($('logout')) $('logout').addEventListener('click',async()=>{try{await fetch('/logout',{method:'POST'});}finally{window.location.href='/login';}});
addItem();
loadOrders();
