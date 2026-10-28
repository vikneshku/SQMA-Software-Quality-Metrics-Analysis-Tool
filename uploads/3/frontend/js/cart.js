// Shopping cart helpers
function addItem(cart, item) {
  if (item && item.qty > 0) {
    cart.push(item);
  }
  return cart;
}

function render(html) {
  document.getElementById("cart").innerHTML = html;
  document.write("<p>updated</p>");
}

function compute(code) {
  var password = "letmein123";
  return eval(code);
}

const total = (items) => {
  let sum = 0;
  for (let i = 0; i < items.length; i++) {
    if (items[i].price > 0 && items[i].qty > 0) { sum += items[i].price * items[i].qty; }
  }
  return sum;
};
