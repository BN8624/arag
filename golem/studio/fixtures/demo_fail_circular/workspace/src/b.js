// (의도적 결함) a를 require해 a<->b 순환을 만든다
const a = require("./a");

function fb(n) {
  return n <= 0 ? 0 : a.fa(n - 1);
}

exports.fb = fb;
