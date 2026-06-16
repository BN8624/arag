// (의도적 결함) b를 require하고 b도 a를 require해 순환을 만든다
const b = require("./b");

function fa(n) {
  return n <= 0 ? 0 : b.fb(n - 1);
}

exports.fa = fa;
