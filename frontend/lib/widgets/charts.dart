import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../utils/format.dart';

class ChartDatum {
  final String label;
  final double value;
  final Color color;
  const ChartDatum(this.label, this.value, this.color);
}

double _niceMax(double v) {
  if (v <= 0) return 1;
  final mag = math.pow(10, (math.log(v) / math.ln10).floor()).toDouble();
  for (final m in [1, 2, 2.5, 5, 10]) {
    if (v * 1.12 <= m * mag) return m * mag;
  }
  return 10 * mag;
}

Widget _axisLabel(String text) => Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Text(text, style: const TextStyle(fontSize: 11, color: FB.muted), overflow: TextOverflow.ellipsis),
    );

Widget _leftLabel(double v, TitleMeta meta) {
  if (v == meta.max && v != 0) return const SizedBox.shrink();
  return Text(v >= 1000 ? '${(v / 1000).toStringAsFixed(1)}k' : v.toStringAsFixed(v < 10 && v != 0 ? 1 : 0),
      style: const TextStyle(fontSize: 10.5, color: FB.muted));
}

FlGridData _grid() => FlGridData(
      show: true,
      drawVerticalLine: false,
      getDrawingHorizontalLine: (_) => const FlLine(color: FB.line, strokeWidth: 1, dashArray: [4, 4]),
    );

/// Coloured bars with the value printed on top — the "Food Rescued by Category" chart.
class CategoryBarChart extends StatelessWidget {
  final List<ChartDatum> data;
  final double height;
  final String unit;
  const CategoryBarChart({super.key, required this.data, this.height = 240, this.unit = ''});

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty || data.every((d) => d.value == 0)) {
      return SizedBox(
          height: height, child: const Center(child: Text('No data yet', style: TextStyle(color: FB.muted))));
    }
    final maxV = _niceMax(data.map((e) => e.value).reduce(math.max));
    return SizedBox(
      height: height,
      child: LayoutBuilder(builder: (context, c) {
        final w = ((c.maxWidth - 40) / data.length * .55).clamp(10.0, 46.0);
        return BarChart(
          BarChartData(
            maxY: maxV,
            minY: 0,
            alignment: BarChartAlignment.spaceAround,
            gridData: _grid(),
            borderData: FlBorderData(show: false),
            barTouchData: BarTouchData(
              enabled: false,
              touchTooltipData: BarTouchTooltipData(
                getTooltipColor: (_) => Colors.transparent,
                tooltipPadding: EdgeInsets.zero,
                tooltipMargin: 3,
                getTooltipItem: (group, gi, rod, ri) => BarTooltipItem(
                  fmtNum(rod.toY),
                  const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: FB.ink),
                ),
              ),
            ),
            titlesData: FlTitlesData(
              topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              leftTitles: AxisTitles(
                  sideTitles: SideTitles(showTitles: true, reservedSize: 36, getTitlesWidget: _leftLabel)),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 28,
                  getTitlesWidget: (v, meta) {
                    final i = v.toInt();
                    if (i < 0 || i >= data.length) return const SizedBox.shrink();
                    return SizedBox(width: w + 30, child: Center(child: _axisLabel(data[i].label)));
                  },
                ),
              ),
            ),
            barGroups: [
              for (var i = 0; i < data.length; i++)
                BarChartGroupData(
                  x: i,
                  showingTooltipIndicators: const [0],
                  barRods: [
                    BarChartRodData(
                      toY: data[i].value,
                      color: data[i].color,
                      width: w,
                      borderRadius: const BorderRadius.vertical(top: Radius.circular(5)),
                    ),
                  ],
                ),
            ],
          ),
        );
      }),
    );
  }
}

class SeriesSpec {
  final String name;
  final Color color;
  final List<double> values;
  const SeriesSpec(this.name, this.color, this.values);
}

/// Grouped bars (e.g. weekly sold / wasted / donated).
class GroupedBarChart extends StatelessWidget {
  final List<String> labels;
  final List<SeriesSpec> series;
  final double height;
  const GroupedBarChart({super.key, required this.labels, required this.series, this.height = 240});

  @override
  Widget build(BuildContext context) {
    final all = series.expand((s) => s.values).toList();
    final maxV = _niceMax(all.isEmpty ? 1 : all.reduce(math.max));
    return Column(children: [
      Legend(series.map((s) => ChartDatum(s.name, 0, s.color)).toList()),
      const SizedBox(height: 10),
      SizedBox(
        height: height,
        child: BarChart(BarChartData(
          maxY: maxV,
          gridData: _grid(),
          borderData: FlBorderData(show: false),
          barTouchData: BarTouchData(
            touchTooltipData: BarTouchTooltipData(
              getTooltipColor: (_) => FB.forestDeep,
              getTooltipItem: (g, gi, rod, ri) => BarTooltipItem(
                '${series[ri].name}\n${fmtNum(rod.toY)} kg',
                const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles:
                AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 36, getTitlesWidget: _leftLabel)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 26,
                getTitlesWidget: (v, meta) {
                  final i = v.toInt();
                  if (i < 0 || i >= labels.length) return const SizedBox.shrink();
                  return _axisLabel(labels[i]);
                },
              ),
            ),
          ),
          barGroups: [
            for (var i = 0; i < labels.length; i++)
              BarChartGroupData(x: i, barsSpace: 3, barRods: [
                for (final s in series)
                  BarChartRodData(
                    toY: i < s.values.length ? s.values[i] : 0,
                    color: s.color,
                    width: 7,
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                  ),
              ]),
          ],
        )),
      ),
    ]);
  }
}

/// History + forecast line with an uncertainty band.
class ForecastChart extends StatelessWidget {
  final List<double> history;
  final List<double> forecast;
  final List<double> lower;
  final List<double> upper;
  final DateTime start; // first forecast day
  final double height;
  const ForecastChart({
    super.key,
    required this.history,
    required this.forecast,
    required this.lower,
    required this.upper,
    required this.start,
    this.height = 260,
  });

  @override
  Widget build(BuildContext context) {
    final n = history.length;
    final hSpots = [for (var i = 0; i < n; i++) FlSpot(i.toDouble(), history[i])];
    final fSpots = <FlSpot>[
      if (n > 0) FlSpot((n - 1).toDouble(), history.last),
      for (var i = 0; i < forecast.length; i++) FlSpot((n + i).toDouble(), forecast[i]),
    ];
    final lo = [for (var i = 0; i < lower.length; i++) FlSpot((n + i).toDouble(), lower[i])];
    final hi = [for (var i = 0; i < upper.length; i++) FlSpot((n + i).toDouble(), upper[i])];
    final all = [...history, ...forecast, ...upper];
    final maxV = _niceMax(all.isEmpty ? 1 : all.reduce(math.max));
    final total = n + forecast.length;
    final step = math.max(1, (total / 7).ceil());
    return Column(children: [
      const Legend([
        ChartDatum('Actual sales', 0, FB.forest),
        ChartDatum('Forecast', 0, FB.amber),
        ChartDatum('80% band', 0, Color(0x55E8A33D)),
      ]),
      const SizedBox(height: 10),
      SizedBox(
        height: height,
        child: LineChart(LineChartData(
          minY: 0,
          maxY: maxV,
          minX: 0,
          maxX: math.max(1, total - 1).toDouble(),
          gridData: _grid(),
          borderData: FlBorderData(show: false),
          lineTouchData: LineTouchData(
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => FB.forestDeep,
              getTooltipItems: (spots) => spots.map((s) {
                if (s.barIndex > 1) return null;
                final d = start.add(Duration(days: s.x.toInt() - n));
                return LineTooltipItem('${fmtDateShort(d)}\n${fmtNum(s.y)}',
                    const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600));
              }).toList(),
            ),
          ),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles:
                AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 36, getTitlesWidget: _leftLabel)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 26,
                interval: step.toDouble(),
                getTitlesWidget: (v, meta) {
                  if (v != v.roundToDouble()) return const SizedBox.shrink();
                  final d = start.add(Duration(days: v.toInt() - n));
                  return _axisLabel(fmtDateShort(d));
                },
              ),
            ),
          ),
          extraLinesData: n > 0
              ? ExtraLinesData(verticalLines: [
                  VerticalLine(
                    x: (n - 1).toDouble(),
                    color: FB.muted.withOpacity(.5),
                    strokeWidth: 1,
                    dashArray: [3, 3],
                    label: VerticalLineLabel(
                      show: true,
                      alignment: Alignment.topRight,
                      style: const TextStyle(fontSize: 10, color: FB.muted),
                      labelResolver: (_) => 'today',
                    ),
                  ),
                ])
              : null,
          betweenBarsData: lo.isNotEmpty && hi.isNotEmpty
              ? [BetweenBarsData(fromIndex: 2, toIndex: 3, color: FB.amber.withOpacity(.18))]
              : [],
          lineBarsData: [
            LineChartBarData(
              spots: hSpots.isEmpty ? [const FlSpot(0, 0)] : hSpots,
              color: FB.forest,
              barWidth: 2.2,
              isCurved: true,
              curveSmoothness: .2,
              preventCurveOverShooting: true,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(show: true, color: FB.forest.withOpacity(.06)),
            ),
            LineChartBarData(
              spots: fSpots.isEmpty ? [const FlSpot(0, 0)] : fSpots,
              color: FB.amber,
              barWidth: 2.6,
              isCurved: true,
              curveSmoothness: .2,
              preventCurveOverShooting: true,
              dashArray: [6, 3],
              dotData: const FlDotData(show: false),
            ),
            LineChartBarData(
                spots: lo.isEmpty ? [const FlSpot(0, 0)] : lo,
                color: Colors.transparent,
                barWidth: 0,
                dotData: const FlDotData(show: false)),
            LineChartBarData(
                spots: hi.isEmpty ? [const FlSpot(0, 0)] : hi,
                color: Colors.transparent,
                barWidth: 0,
                dotData: const FlDotData(show: false)),
          ],
        )),
      ),
    ]);
  }
}

/// Donut with legend.
class DonutChart extends StatelessWidget {
  final List<ChartDatum> data;
  final String centerLabel;
  final String centerValue;
  final double size;
  const DonutChart({super.key, required this.data, this.centerLabel = '', this.centerValue = '', this.size = 170});

  @override
  Widget build(BuildContext context) {
    final nonZero = data.where((d) => d.value > 0).toList();
    final chart = SizedBox(
      width: size,
      height: size,
      child: Stack(alignment: Alignment.center, children: [
        PieChart(PieChartData(
          sectionsSpace: 2,
          centerSpaceRadius: size * .32,
          startDegreeOffset: -90,
          sections: nonZero.isEmpty
              ? [PieChartSectionData(value: 1, color: FB.line, radius: size * .16, showTitle: false)]
              : nonZero
                  .map((d) => PieChartSectionData(value: d.value, color: d.color, radius: size * .16, showTitle: false))
                  .toList(),
        )),
        Column(mainAxisSize: MainAxisSize.min, children: [
          Text(centerValue, style: FB.display(22)),
          Text(centerLabel, style: const TextStyle(fontSize: 11, color: FB.muted)),
        ]),
      ]),
    );
    final legend = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: data
          .map((d) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(width: 10, height: 10, decoration: BoxDecoration(color: d.color, borderRadius: BorderRadius.circular(3))),
                  const SizedBox(width: 8),
                  Text(d.label, style: const TextStyle(fontSize: 13)),
                  const SizedBox(width: 10),
                  Text(fmtNum(d.value), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                ]),
              ))
          .toList(),
    );
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: 24,
      runSpacing: 16,
      children: [chart, legend],
    );
  }
}

class Legend extends StatelessWidget {
  final List<ChartDatum> items;
  const Legend(this.items, {super.key});
  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 16,
        runSpacing: 6,
        children: items
            .map((d) => Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(width: 12, height: 4, decoration: BoxDecoration(color: d.color, borderRadius: BorderRadius.circular(2))),
                  const SizedBox(width: 6),
                  Text(d.label, style: const TextStyle(fontSize: 12, color: FB.muted)),
                ]))
            .toList(),
      );
}

/// Area line for a single monthly series.
class TrendLineChart extends StatelessWidget {
  final List<String> labels;
  final List<double> values;
  final Color color;
  final double height;
  const TrendLineChart(
      {super.key, required this.labels, required this.values, this.color = FB.leaf, this.height = 220});

  @override
  Widget build(BuildContext context) {
    final maxV = _niceMax(values.isEmpty ? 1 : values.reduce(math.max));
    return SizedBox(
      height: height,
      child: LineChart(LineChartData(
        minY: 0,
        maxY: maxV,
        minX: 0,
        maxX: math.max(1, values.length - 1).toDouble(),
        gridData: _grid(),
        borderData: FlBorderData(show: false),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => FB.forestDeep,
            getTooltipItems: (spots) => spots
                .map((s) => LineTooltipItem(
                      '${labels[s.x.toInt().clamp(0, labels.length - 1)]}\n${fmtNum(s.y)}',
                      const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
                    ))
                .toList(),
          ),
        ),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles:
              AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 36, getTitlesWidget: _leftLabel)),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 26,
              interval: 1,
              getTitlesWidget: (v, meta) {
                final i = v.toInt();
                if (v != v.roundToDouble() || i < 0 || i >= labels.length) return const SizedBox.shrink();
                return _axisLabel(labels[i].split(' ').first);
              },
            ),
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: values.isEmpty
                ? [const FlSpot(0, 0)]
                : [for (var i = 0; i < values.length; i++) FlSpot(i.toDouble(), values[i])],
            isCurved: true,
            preventCurveOverShooting: true,
            color: color,
            barWidth: 3,
            dotData: FlDotData(
              show: true,
              getDotPainter: (s, p, b, i) =>
                  FlDotCirclePainter(radius: 3.5, color: Colors.white, strokeWidth: 2, strokeColor: color),
            ),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [color.withOpacity(.28), color.withOpacity(.02)],
              ),
            ),
          ),
        ],
      )),
    );
  }
}
