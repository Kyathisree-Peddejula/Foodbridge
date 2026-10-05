import 'package:flutter_test/flutter_test.dart';
import 'package:foodbridge/utils/format.dart';
import 'package:foodbridge/utils/json.dart';

void main() {
  test('json helpers are forgiving', () {
    expect(toD('12.5'), 12.5);
    expect(toD(null, 3), 3);
    expect(toI(4.6), 5);
    expect(toL({'results': [{'a': 1}]}).length, 1);
    expect(toL([{'a': 1}, 2]).length, 1);
  });

  test('formatting', () {
    expect(expiryLabel(0), 'Expires today');
    expect(expiryLabel(-2), 'Expired 2d ago');
    expect(titleCase('in_transit'), 'In Transit');
  });
}
