using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using ArcGIS.Core.CIM;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Core;
using ArcGIS.Desktop.Core.Geoprocessing;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Layouts;
using ArcGIS.Desktop.Mapping;

namespace ProBridge
{
    internal static class Handlers
    {
        public static Task<object> ExecuteAsync(string cmd, JsonElement args)
        {
            switch (cmd)
            {
                case "ping":
                    return QueuedTask.Run<object>(() => Ping());

                case "list_layers":
                    return QueuedTask.Run<object>(() => ListLayers(args));

                case "add_layer":
                    return QueuedTask.Run<object>(() => AddLayer(args));

                case "remove_layer":
                    return QueuedTask.Run<object>(() => RemoveLayer(args));

                case "clear_layers":
                    return QueuedTask.Run<object>(() => ClearLayers(args));

                case "get_layer_extent":
                    return QueuedTask.Run<object>(() => GetLayerExtent(args));

                case "zoom_to_extent":
                    return OnUIAsync(() => ZoomToExtentAsync(args));

                case "refresh":
                    // Redraw is an MCT API, not a UI-thread one: wrapping it in the
                    // dispatcher throws "must be called on the thread this object was created on".
                    return QueuedTask.Run<object>(() =>
                    {
                        var view = MapView.Active;
                        if (view == null) return (object)new { refreshed = false, reason = "no active map view" };
                        view.Redraw(true);
                        return new { refreshed = true };
                    });

                case "activate_map":
                    return ActivateMapAsync(args);

                case "bind_map_frame":
                    return QueuedTask.Run<object>(() => BindMapFrame(args));

                case "list_elements":
                    return QueuedTask.Run<object>(() => ListElements(args));

                case "set_text":
                    return QueuedTask.Run<object>(() => SetText(args));

                case "set_visible":
                    return QueuedTask.Run<object>(() => SetVisible(args));

                case "set_layer_render":
                    return QueuedTask.Run<object>(() => SetLayerRender(args));

                case "set_symbology":
                    return QueuedTask.Run<object>(() => SetSymbology(args));

                case "add_surrounds":
                    return QueuedTask.Run<object>(() => AddSurrounds(args));

                case "create_map":
                    return QueuedTask.Run<object>(() => CreateMap(args));

                case "create_panel_layout":
                    return QueuedTask.Run<object>(() => CreatePanelLayout(args));

                case "save":
                    return SaveProjectAsync();

                case "import_layout":
                    return ImportLayoutAsync(args);

                case "open_layout":
                    return OpenLayoutAsync(args);

                case "export_layout":
                    return QueuedTask.Run<object>(() => ExportLayout(args));

                case "run_gp":
                    // ExecuteToolAsync manages its own threading. Wrapping it in
                    // QueuedTask deadlocks; the non-modal overload below is also
                    // the only one that works without a progress dialog.
                    return RunGpAsync(args);

                case "debug_threads":
                    return DebugThreadsAsync();

                case "debug_ui":
                    return QueuedTask.Run<object>(() => DebugUi());

                case "show_agent":
                    return OnUIAsync(() =>
                        Task.FromResult(AgentPaneViewModel.ShowOrWindow()));

                default:
                    throw new InvalidOperationException($"unknown cmd: {cmd}");
            }
        }

        private static async Task<object> DebugThreadsAsync()
        {
            var bg = System.Threading.Thread.CurrentThread.ManagedThreadId;
            var result = new Dictionary<string, object>
            {
                ["background"] = bg,
                ["appNull"] = Application.Current == null
            };

            int ui = -1;
            string err = null;
            int maps = -1;
            int layouts = -1;

            try
            {
                await Application.Current.Dispatcher.InvokeAsync(() =>
                {
                    ui = System.Threading.Thread.CurrentThread.ManagedThreadId;
                    try
                    {
                        maps = Project.Current.GetItems<MapProjectItem>().Count();
                        layouts = Project.Current.GetItems<LayoutProjectItem>().Count();
                    }
                    catch (Exception ex)
                    {
                        err = ex.Message;
                    }
                });
            }
            catch (Exception ex)
            {
                err = "dispatch: " + ex.Message;
            }

            result["ui"] = ui;
            result["same"] = bg == ui;
            result["mapsOnUi"] = maps;
            result["layoutsOnUi"] = layouts;
            result["error"] = err;
            return result;
        }

        /// <summary>
        /// Reports whether the agent dock pane exists and is on screen. There is no
        /// reliable way to see this from outside Pro, so the pane reports itself.
        /// </summary>
        private static object DebugUi()
        {
            var pane = ArcGIS.Desktop.Framework.FrameworkApplication.DockPaneManager
                .Find("ProBridge_AgentPane");
            return new
            {
                found = pane != null,
                visible = pane?.IsVisible ?? false,
                caption = pane?.Caption,
                webviewProcs = System.Diagnostics.Process.GetProcessesByName("msedgewebview2").Length
            };
        }

        private static object Ping()
        {
            var proj = Project.Current;
            return new
            {
                bridge = "0.3.0",
                project = proj?.Name,
                projectPath = proj?.Path,
                maps = proj?.GetItems<MapProjectItem>().Select(i => i.Name).ToArray(),
                layouts = proj?.GetItems<LayoutProjectItem>().Select(i => i.Name).ToArray(),
                activeMap = MapView.Active?.Map?.Name
            };
        }

        private static object ListLayers(JsonElement args)
        {
            var map = GetMap(args);
            return EnumerateLayers(map.Layers).Select(l => new
            {
                name = l.Name,
                type = l.GetType().Name,
                visible = l.IsVisible
            }).ToArray();
        }

        private static object AddLayer(JsonElement args)
        {
            var map = GetMap(args);
            var path = Path.GetFullPath(Require(args, "path"));
            var name = Optional(args, "name") ?? Path.GetFileNameWithoutExtension(path);
            var layer = LayerFactory.Instance.CreateLayer(new Uri(path), map, 0, name);
            if (layer == null) throw new InvalidOperationException($"layer not created: {path}");
            return new { name = layer.Name, path };
        }

        private static object RemoveLayer(JsonElement args)
        {
            var map = GetMap(args);
            var name = Require(args, "name");
            var (layer, parent) = FindLayerWithParent(map.Layers, name);
            if (layer == null)
                throw new InvalidOperationException($"layer not found: {name}");
            if (parent == null) map.RemoveLayer(layer);
            else parent.RemoveLayer(layer);
            return new { removed = name };
        }

        private static object ClearLayers(JsonElement args)
        {
            var map = GetMap(args);
            var prefix = Optional(args, "prefix") ?? "pb_";
            var targets = new List<(Layer Layer, GroupLayer Parent)>();
            CollectLayers(map.Layers, prefix, null, targets);
            foreach (var (layer, parent) in targets)
            {
                if (parent == null) map.RemoveLayer(layer);
                else parent.RemoveLayer(layer);
            }
            return new { removed = targets.Count, prefix };
        }

        private static object GetLayerExtent(JsonElement args)
        {
            var layer = FindLayer(args);
            var env = layer.QueryExtent();
            if (env == null) throw new InvalidOperationException($"no extent: {layer.Name}");
            return new
            {
                xmin = env.XMin,
                ymin = env.YMin,
                xmax = env.XMax,
                ymax = env.YMax,
                wkid = env.SpatialReference?.Wkid ?? 0
            };
        }

        private static async Task<object> ZoomToExtentAsync(JsonElement args)
        {
            var view = MapView.Active
                       ?? throw new InvalidOperationException(
                           "no active map view (a layout pane may be in front; run activate_map first)");
            var sr = view.Map.SpatialReference;
            var env = EnvelopeBuilderEx.CreateEnvelope(
                Num(args, "xmin"), Num(args, "ymin"), Num(args, "xmax"), Num(args, "ymax"), sr);

            var ms = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("duration_ms", out var d)
                ? d.GetDouble()
                : 800;

            await view.ZoomToAsync(env, TimeSpan.FromMilliseconds(ms));
            return new { zoomed = true, duration_ms = ms };
        }

        private static async Task<object> ImportLayoutAsync(JsonElement args)
        {
            var path = Path.GetFullPath(Require(args, "pagx"));
            if (!File.Exists(path)) throw new FileNotFoundException(path);

            // Both ItemFactory.Create and Project.AddItem are MCT-only APIs.
            // Calling AddItem from the WPF dispatcher throws CalledOnWrongThreadException,
            // so the whole import has to stay inside one QueuedTask.
            var added = await QueuedTask.Run(() =>
            {
                var before = Project.Current.GetItems<LayoutProjectItem>().Select(i => i.Name).ToList();

                var item = ItemFactory.Instance.Create(path, ItemFactory.ItemType.PathItem) as IProjectItem;
                if (item == null) throw new InvalidOperationException("cannot create project item for " + path);

                Project.Current.AddItem(item);

                var after = Project.Current.GetItems<LayoutProjectItem>().Select(i => i.Name).ToList();
                return after.FirstOrDefault(n => !before.Contains(n));
            });

            if (added == null)
                throw new InvalidOperationException("layout not imported (already present?)");

            return new { name = added };
        }

        private static async Task<object> OpenLayoutAsync(JsonElement args)
        {
            var name = Require(args, "name");

            var layout = await QueuedTask.Run(() =>
                Project.Current.GetItems<LayoutProjectItem>()
                    .FirstOrDefault(i => i.Name == name)?.GetLayout());
            if (layout == null) throw new InvalidOperationException($"layout not found: {name}");

            // Pane creation is a UI operation; the layout itself must be fetched on the MCT.
            await OnUIAsync(async () =>
            {
                await ProApp.Panes.CreateLayoutPaneAsync(layout);
                return (object)null;
            });

            return new { opened = name };
        }

        private static async Task<object> SaveProjectAsync()
        {
            // Without this, everything an agent does (imported layouts, added layers)
            // is lost when Pro closes. SaveAsync touches Dispatcher-owned state, so it
            // has to run on the UI thread.
            var path = await QueuedTask.Run(() => Project.Current.Path);
            await OnUIAsync(async () =>
            {
                await Project.Current.SaveAsync();
                return (object)null;
            });
            return new { saved = path };
        }

        private static async Task<object> ActivateMapAsync(JsonElement args)
        {
            // Opening a layout pane clears MapView.Active, which breaks every map command
            // afterwards. This puts the map view back in front.
            var map = await QueuedTask.Run(() => GetMap(args));

            await OnUIAsync(async () =>
            {
                await ProApp.Panes.CreateMapPaneAsync(map);
                return (object)null;
            });

            return new { activated = map.Name };
        }

        /// <summary>
        /// Points a layout's map frame at a map, and optionally frames a layer inside it.
        /// An imported .pagx keeps its own (empty) map frame, so this is what makes a
        /// template actually usable.
        /// </summary>
        private static object BindMapFrame(JsonElement args)
        {
            var layoutName = Require(args, "layout");
            var layout = Project.Current.GetItems<LayoutProjectItem>()
                             .FirstOrDefault(i => i.Name == layoutName)?.GetLayout()
                         ?? throw new InvalidOperationException($"layout not found: {layoutName}");

            var frames = layout.GetElementsAsFlattenedList().OfType<MapFrame>().ToList();
            if (frames.Count == 0) throw new InvalidOperationException($"layout has no map frame: {layoutName}");

            var index = 0;
            if (args.ValueKind == JsonValueKind.Object && args.TryGetProperty("frame", out var fi))
                index = fi.GetInt32();
            if (index < 0 || index >= frames.Count)
                throw new InvalidOperationException($"frame index out of range: {index} (layout has {frames.Count})");

            var frame = frames[index];
            var map = GetMap(args);
            frame.SetMap(map);

            var layerName = Optional(args, "layer");
            if (layerName != null)
            {
                var layer = map.Layers.FirstOrDefault(l => l.Name == layerName)
                            ?? throw new InvalidOperationException($"layer not found: {layerName}");

                var ratio = 0.075;
                if (args.ValueKind == JsonValueKind.Object && args.TryGetProperty("ratio", out var r))
                    ratio = r.GetDouble();

                var bounds = frame.GetBounds(false);
                var aspect = bounds.Height > 0 ? bounds.Width / bounds.Height : 0;

                var env = layer.QueryExtent() ?? throw new InvalidOperationException($"no extent: {layerName}");
                frame.SetCamera(PadExtent(env, ratio, aspect));
            }

            return new
            {
                layout = layoutName,
                map = map.Name,
                frame = index,
                frames = frames.Count,
                layer = layerName
            };
        }

        private static Envelope PadExtent(Envelope env, double ratio, double aspect)
        {
            var w = env.Width;
            var h = env.Height;
            if (w <= 0 || h <= 0) throw new InvalidOperationException("layer extent is empty");

            // Grow the short side first so the margin stays even in a frame of a different aspect.
            if (aspect > 0)
            {
                if (w / h < aspect) w = h * aspect;
                else h = w / aspect;
            }
            w *= 1.0 + 2.0 * ratio;
            h *= 1.0 + 2.0 * ratio;

            var cx = env.XMin + env.Width / 2.0;
            var cy = env.YMin + env.Height / 2.0;

            return EnvelopeBuilderEx.CreateEnvelope(
                cx - w / 2.0, cy - h / 2.0,
                cx + w / 2.0, cy + h / 2.0,
                env.SpatialReference);
        }

        /// <summary>
        /// Pins a raster's renderer. Pro applies a percentile stretch to RGB rasters
        /// by default, which wrecks colours that were already baked in (a hypsometric
        /// tint turns pink). mode=rgb renders the bytes as they are.
        /// </summary>
        private static object SetLayerRender(JsonElement args)
        {
            var layer = FindLayer(args);
            if (!(layer is BasicRasterLayer raster))
                throw new InvalidOperationException($"not a raster layer: {layer.Name}");

            var mode = (Optional(args, "mode") ?? "rgb").ToLowerInvariant();
            var red = (int)OptNum(args, "red", 0);
            var green = (int)OptNum(args, "green", 1);
            var blue = (int)OptNum(args, "blue", 2);
            CIMRasterColorizer colorizer;
            switch (mode)
            {
                case "rgb":
                    // A bare RGB colorizer has no bands and renders black; spell
                    // them out exactly as the raster_rgb branch does.
                    colorizer = new CIMRasterRGBColorizer
                    {
                        UseRedBand = true,
                        UseGreenBand = true,
                        UseBlueBand = true,
                        RedBandIndex = red,
                        GreenBandIndex = green,
                        BlueBandIndex = blue,
                        StretchType = RasterStretchType.None
                    };
                    break;
                case "stretch":
                    colorizer = new CIMRasterStretchColorizer();
                    break;
                default:
                    throw new InvalidOperationException($"unsupported mode: {mode} (rgb/stretch)");
            }

            raster.SetColorizer(colorizer);
            ApplyOpacity(layer, args);
            return new
            {
                layer = layer.Name,
                mode,
                bands = mode == "rgb" ? new[] { red, green, blue } : null
            };
        }

        /// <summary>
        /// Rewrites a layer's renderer / colorizer through CIM. This is the only way to keep
        /// baked colours intact: Pro's default display pipeline re-stretches raster bands, so an
        /// already-mapped hypsometric tint turns teal. StretchType.None (or real colour stops)
        /// is what the GUI's "Stretch type = None" does — there was no bridge command for it.
        ///
        /// kind=raster_stretch: colors[] (#RRGGBB, 2..12 stops), stretch=none|minmax|percentclip|stddev,
        ///                     min_pct, max_pct, std_dev, gamma, invert
        /// kind=feature:        fill=#RRGGBB|none, fill_alpha, outline=#RRGGBB, width (points)
        /// </summary>
        private static object SetSymbology(JsonElement args)
        {
            var layer = FindLayer(args);
            var kind = (Optional(args, "kind") ?? "feature").ToLowerInvariant();

            if (kind == "raster_stretch")
            {
                if (!(layer is BasicRasterLayer raster))
                    throw new InvalidOperationException($"not a raster layer: {layer.Name}");

                var stretch = (Optional(args, "stretch") ?? "none").ToLowerInvariant();
                var colorizer = new CIMRasterStretchColorizer
                {
                    StretchType = stretch switch
                    {
                        "none" => RasterStretchType.None,
                        "minmax" => RasterStretchType.MinimumMaximum,
                        "stddev" => RasterStretchType.StandardDeviations,
                        "percentclip" => RasterStretchType.PercentMinimumMaximum,
                        _ => throw new InvalidOperationException($"unsupported stretch: {stretch} (none/minmax/percentclip/stddev)")
                    },
                    ColorRamp = BuildColorRamp(args)
                };

                if (colorizer.StretchType == RasterStretchType.PercentMinimumMaximum)
                {
                    colorizer.MinPercent = OptNum(args, "min_pct", 0.5);
                    colorizer.MaxPercent = OptNum(args, "max_pct", 99.8);
                }
                else if (colorizer.StretchType == RasterStretchType.StandardDeviations)
                {
                    colorizer.StandardDeviationParam = OptNum(args, "std_dev", 2.0);
                }

                var gamma = OptNum(args, "gamma", 1.0);
                if (Math.Abs(gamma - 1.0) > 1e-6)
                {
                    colorizer.GammaValue = gamma;
                    colorizer.UseGammaStretch = true;
                }

                colorizer.Invert = OptFlag(args, "invert", false);

                raster.SetColorizer(colorizer);
                ApplyOpacity(layer, args);
                return new
                {
                    layer = layer.Name,
                    kind,
                    stretch = colorizer.StretchType.ToString(),
                    colors = CountColors(args)
                };
            }

            if (kind == "raster_rgb")
            {
                if (!(layer is BasicRasterLayer rgbLayer))
                    throw new InvalidOperationException($"not a raster layer: {layer.Name}");

                // Bands must be spelled out: a bare CIMRasterRGBColorizer has no bands and
                // renders the raster solid black. SetLayerRender now sets them too; this
                // branch remains the explicit-band path for baked RGB.
                var red = (int)OptNum(args, "red", 0);
                var green = (int)OptNum(args, "green", 1);
                var blue = (int)OptNum(args, "blue", 2);

                var rgb = new CIMRasterRGBColorizer
                {
                    UseRedBand = true,
                    UseGreenBand = true,
                    UseBlueBand = true,
                    RedBandIndex = red,
                    GreenBandIndex = green,
                    BlueBandIndex = blue,
                    StretchType = RasterStretchType.None
                };

                rgbLayer.SetColorizer(rgb);
                ApplyOpacity(layer, args);

                return new { layer = layer.Name, kind, bands = new[] { red, green, blue }, stretch = "None" };
            }

            if (kind == "feature")
            {
                if (!(layer is FeatureLayer fl))
                    throw new InvalidOperationException($"not a feature layer: {layer.Name}");

                var isPoint = fl.ShapeType == esriGeometryType.esriGeometryPoint
                              || fl.ShapeType == esriGeometryType.esriGeometryMultipoint;
                var symbol = BuildFeatureSymbol(fl.ShapeType, args);
                fl.SetRenderer(new CIMSimpleRenderer { Symbol = new CIMSymbolReference { Symbol = symbol } });
                ApplyOpacity(layer, args);

                return new
                {
                    layer = layer.Name,
                    kind,
                    shape = fl.ShapeType.ToString(),
                    fill = Optional(args, "fill") ?? (isPoint ? "#D73027" : "none"),
                    outline = isPoint ? null : Optional(args, "outline") ?? "#3F3F3F",
                    width = isPoint ? (double?)null : OptNum(args, "width", 1.0),
                    halo = isPoint ? Optional(args, "halo") ?? "#FFFFFF" : null
                };
            }

            // 点：圆 / 方 / 三角 / 菱形 + 白色晕圈（Imhof 的图底分离；小圆圈最不容易压住底图）
            if (kind == "point" || kind == "point_symbol")
            {
                if (!(layer is FeatureLayer pointLayer))
                    throw new InvalidOperationException($"not a feature layer: {layer.Name}");
                if (pointLayer.ShapeType != esriGeometryType.esriGeometryPoint
                    && pointLayer.ShapeType != esriGeometryType.esriGeometryMultipoint)
                    throw new InvalidOperationException($"layer is not points: {pointLayer.ShapeType}");

                var fillHex = Optional(args, "fill") ?? "#D73027";
                var size = OptNum(args, "size", 8.0);
                var markerName = (Optional(args, "marker") ?? "circle").ToLowerInvariant();
                var style = ParseMarkerStyle(markerName);

                var symbol = (CIMPointSymbol)SymbolFactory.Instance
                    .ConstructPointSymbol(ParseColor(fillHex), size, style);

                // HaloSize/HaloSymbol exist on CIMPointSymbol — that is the halo behind a marker,
                // the same trick labels use to stay readable over busy raster backgrounds.
                var haloHex = Optional(args, "halo") ?? "#FFFFFF";
                var haloSize = OptNum(args, "halo_size", Math.Max(0.6, size * 0.12));
                if (!haloHex.Equals("none", StringComparison.OrdinalIgnoreCase))
                {
                    symbol.HaloSymbol = new CIMPolygonSymbol
                    {
                        SymbolLayers = new CIMSymbolLayer[]
                        {
                            new CIMSolidFill { Color = ParseColor(haloHex) }
                        }
                    };
                    symbol.HaloSize = haloSize;
                }

                pointLayer.SetRenderer(new CIMSimpleRenderer
                {
                    Symbol = new CIMSymbolReference { Symbol = symbol }
                });
                ApplyOpacity(pointLayer, args);

                return new
                {
                    layer = pointLayer.Name,
                    kind = "point",
                    marker = markerName,
                    size,
                    fill = fillHex,
                    halo = haloHex
                };
            }

            if (kind == "feature_breaks" || kind == "class_breaks")
            {
                if (!(layer is FeatureLayer breakLayer))
                    throw new InvalidOperationException($"not a feature layer: {layer.Name}");
                return ApplyClassBreaks(breakLayer, args);
            }

            throw new InvalidOperationException(
                $"unsupported kind: {kind} (raster_stretch/raster_rgb/raster_classify/feature/feature_breaks/point)");
        }

        /// <summary>
        /// 分级设色（choropleth）：把一个数值字段切成 N 级，每级一个颜色。
        /// method: natural=Jenks 自然断点（偏态数据首选）、quantile=分位数（等数量）、
        ///         equal=等间距、manual=用 breaks[] 指定。
        /// 依据：数据偏态时用自然断点，等数量能拉出内部差异；顺序型数据用明度主导的顺序色阶。
        /// 见 docs/美化规则.md 的「分级与配色」一节。
        /// </summary>
        private static object ApplyClassBreaks(FeatureLayer layer, JsonElement args)
        {
            var field = Optional(args, "field")
                        ?? throw new InvalidOperationException("missing arg: field");

            var method = (Optional(args, "method") ?? "natural").ToLowerInvariant();
            var values = ReadNumbers(layer, field);

            double[] bounds;
            var classes = (int)OptNum(args, "classes", 5);
            if (method == "manual")
            {
                if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty("breaks", out var arr)
                    || arr.ValueKind != JsonValueKind.Array)
                    throw new InvalidOperationException("method=manual needs breaks[]");
                bounds = arr.EnumerateArray().Select(e => e.GetDouble()).ToArray();
                classes = bounds.Length;
            }
            else
            {
                if (classes < 2 || classes > 12)
                    throw new InvalidOperationException("classes must be 2..12");
                bounds = method switch
                {
                    "quantile" => QuantileBreaks(values, classes),
                    "equal" => EqualBreaks(values, classes),
                    "natural" => NaturalBreaks(values, classes),
                    _ => throw new InvalidOperationException($"unsupported method: {method} (natural/quantile/equal/manual)")
                };
            }

            // manual 分支的 classes 来自 breaks[]，这里统一再校验一次
            if (classes < 2 || classes > 12)
                throw new InvalidOperationException("classes must be 2..12");
            if (classes > 7 && CountColors(args) < classes)
                throw new InvalidOperationException(
                    "classes > 7 requires an explicit colors[] with at least classes stops; " +
                    "use 3-7 classes with the built-in palette");

            var palette = ReadPalette(args, classes);
            var fillAlpha = OptNum(args, "fill_alpha", 100);
            var outlineHex = Optional(args, "outline") ?? "#7A7A7A";
            var width = OptNum(args, "width", 0.4);

            var lower = OptNum(args, "min", values.Min());
            if (lower > bounds[0])
                throw new InvalidOperationException(
                    $"min ({lower:0.###}) is above the first class break ({bounds[0]:0.###})");

            // Manual breaks must be strictly increasing; computed breaks are already
            // deduped, but validating here keeps both paths honest.
            for (var i = 1; i < bounds.Length; i++)
                if (bounds[i] <= bounds[i - 1])
                    throw new InvalidOperationException(
                        $"breaks must be strictly increasing (index {i}: {bounds[i - 1]:0.###} -> {bounds[i]:0.###})");

            var span = Math.Abs(bounds[bounds.Length - 1] - lower);
            var decimals = span >= 100 ? 0
                         : span >= 10 ? 1
                         : span >= 1 ? 2
                         : span >= 0.1 ? 3
                         : span >= 0.01 ? 4
                         : 6;
            var numberFormat = decimals == 0 ? "0" : "0." + new string('#', decimals);
            string Format(double v) => v.ToString(numberFormat, System.Globalization.CultureInfo.InvariantCulture);

            var breaks = new CIMClassBreak[bounds.Length];
            var rows = new List<object>();
            for (var i = 0; i < bounds.Length; i++)
            {
                var up = bounds[i];
                var fill = palette[i % palette.Count];
                var swatch = (CIMRGBColor)fill;
                // Classes are (previous upper, upper]; the first is <= first upper.
                // Avoid the old "1 - 1", "1 - 2" overlap.
                var label = i == 0
                    ? $"≤ {Format(up)}"
                    : $"> {Format(bounds[i - 1])} - {Format(up)}";

                breaks[i] = new CIMClassBreak
                {
                    UpperBound = up,
                    Label = label,
                    Symbol = new CIMSymbolReference
                    {
                        Symbol = BuildClassSymbol(layer.ShapeType, swatch, outlineHex, width, fillAlpha)
                    }
                };
                rows.Add(new { label, color = Hex(swatch), upper = up });
            }

            var renderer = new CIMClassBreaksRenderer
            {
                Field = field,
                ClassificationMethod = ClassificationMethod.Manual,
                MinimumBreak = lower,
                Breaks = breaks,
                ColorRamp = OptFlag(args, "ramp", false) ? BuildColorRamp(args) : null
            };

            layer.SetRenderer(renderer);
            ApplyOpacity(layer, args);

            return new
            {
                layer = layer.Name,
                kind = "feature_breaks",
                field,
                method,
                classes = bounds.Length,
                minimum = lower,
                breaks = rows
            };
        }

        private static CIMSymbol BuildClassSymbol(esriGeometryType shape, CIMColor fill,
                                                  string outlineHex, double width, double fillAlpha)
        {
            if (shape == esriGeometryType.esriGeometryPolyline || shape == esriGeometryType.esriGeometryLine)
            {
                // A line has no fill: use the class colour as the stroke colour,
                // otherwise every class renders with the same outline colour.
                var lineStroke = new CIMSolidStroke { Color = fill, Width = (float)width };
                return new CIMLineSymbol { SymbolLayers = new CIMSymbolLayer[] { lineStroke } };
            }

            if (shape == esriGeometryType.esriGeometryPoint || shape == esriGeometryType.esriGeometryMultipoint)
            {
                var pointFill = (CIMRGBColor)fill;
                pointFill.Alpha = (float)fillAlpha;
                var point = (CIMPointSymbol)SymbolFactory.Instance
                    .ConstructPointSymbol(pointFill, 8, SimpleMarkerStyle.Circle);
                return point;
            }

            var stroke = new CIMSolidStroke { Color = ParseColor(outlineHex), Width = (float)width };
            var solid = (CIMRGBColor)fill;
            solid.Alpha = (float)fillAlpha;
            return new CIMPolygonSymbol
            {
                SymbolLayers = new CIMSymbolLayer[] { stroke, new CIMSolidFill { Color = solid } }
            };
        }

        private static SimpleMarkerStyle ParseMarkerStyle(string markerName)
        {
            switch (markerName)
            {
                case "square": return SimpleMarkerStyle.Square;
                case "triangle": return SimpleMarkerStyle.Triangle;
                case "diamond": return SimpleMarkerStyle.Diamond;
                case "cross": return SimpleMarkerStyle.Cross;
                default: return SimpleMarkerStyle.Circle;
            }
        }

        private static string Hex(CIMRGBColor c) =>
            $"#{To255(c.R):X2}{To255(c.G):X2}{To255(c.B):X2}";

        private static int To255(float v) => (int)Math.Round(Math.Max(0f, Math.Min(255f, v)));

        /// <summary>读图层某个数值字段的全部非空值。QueuedTask 内调用。</summary>
        private static List<double> ReadNumbers(FeatureLayer layer, string field)
        {
            var values = new List<double>();
            using (var fc = layer.GetFeatureClass())
            {
                var idx = fc.GetDefinition().FindField(field);
                if (idx < 0) throw new InvalidOperationException($"field not found: {field}");

                using (var cursor = fc.Search(null, false))
                {
                    while (cursor.MoveNext())
                    {
                        using (var row = cursor.Current)
                        {
                            var raw = row[idx];
                            if (raw == null || raw == DBNull.Value) continue;
                            try
                            {
                                var d = Convert.ToDouble(raw);
                                if (!double.IsNaN(d) && !double.IsInfinity(d)) values.Add(d);
                            }
                            catch (Exception)
                            {
                                // 非数值字段直接忽略，交给 upstream 报错
                            }
                        }
                    }
                }
            }

            if (values.Count == 0) throw new InvalidOperationException($"field has no numeric values: {field}");
            values.Sort();
            if (values[0] == values[values.Count - 1])
                throw new InvalidOperationException($"field has no variation: {field}");
            return values;
        }

        private static double NextBreak(double prev) => Math.BitIncrement(prev);

        private static double[] EqualBreaks(List<double> sorted, int classes)
        {
            var lo = sorted[0];
            var hi = sorted[sorted.Count - 1];
            var span = Math.Max(hi - lo, 1e-9);
            var bounds = new double[classes];
            for (var i = 0; i < classes; i++) bounds[i] = lo + span * (i + 1) / classes;
            bounds[classes - 1] = hi;
            for (var i = 1; i < classes; i++)
                if (bounds[i] <= bounds[i - 1]) bounds[i] = NextBreak(bounds[i - 1]);
            return bounds;
        }

        private static double[] QuantileBreaks(List<double> sorted, int classes)
        {
            var n = sorted.Count;
            var bounds = new double[classes];
            for (var i = 0; i < classes; i++)
            {
                var pos = (int)Math.Round((i + 1) * (double)n / classes) - 1;
                bounds[i] = sorted[Math.Max(0, Math.Min(n - 1, pos))];
            }
            bounds[classes - 1] = sorted[n - 1];
            // 去重：分位数可能落在同一个值上，保证严格递增
            for (var i = 1; i < classes; i++)
                if (bounds[i] <= bounds[i - 1]) bounds[i] = NextBreak(bounds[i - 1]);
            return bounds;
        }

        /// <summary>
        /// Fisher-Jenks 最优分级（组内方差和最小）。O(k·n²)，所以超过 4000 个值先等距抽样——
        /// 分界点对抽样不敏感，够用且不会卡住 QueuedTask。
        /// </summary>
        private static double[] NaturalBreaks(List<double> sorted, int classes)
        {
            var v = sorted;
            if (v.Count > 4000)
            {
                var step = (int)Math.Ceiling(v.Count / 4000.0);
                var sampled = new List<double>();
                for (var i = 0; i < v.Count; i += step) sampled.Add(v[i]);
                if (sampled[sampled.Count - 1] != v[v.Count - 1]) sampled.Add(v[v.Count - 1]);
                v = sampled;
            }

            var n = v.Count;
            if (n <= classes)
            {
                var trivial = new double[classes];
                for (var i = 0; i < classes; i++) trivial[i] = v[Math.Min(n - 1, i)];
                trivial[classes - 1] = v[n - 1];
                for (var i = 1; i < classes; i++)
                    if (trivial[i] <= trivial[i - 1]) trivial[i] = NextBreak(trivial[i - 1]);
                return trivial;
            }

            var mat1 = new double[n + 1, classes + 1];
            var mat2 = new int[n + 1, classes + 1];
            for (var i = 1; i <= classes; i++)
            {
                mat1[1, i] = 0;
                mat2[1, i] = 1;
                for (var j = 2; j <= n; j++) mat1[j, i] = double.MaxValue;
            }

            for (var l = 2; l <= n; l++)
            {
                double sum = 0, sumSq = 0;
                var w = 0;
                for (var m = 1; m <= l; m++)
                {
                    var i3 = l - m + 1;
                    var val = v[i3 - 1];
                    w++;
                    sum += val;
                    sumSq += val * val;
                    var variance = sumSq - (sum * sum) / w;
                    var i4 = i3 - 1;
                    if (i4 == 0) continue;
                    for (var j = 2; j <= classes; j++)
                    {
                        if (mat1[l, j] < variance + mat1[i4, j - 1]) continue;
                        mat1[l, j] = variance + mat1[i4, j - 1];
                        mat2[l, j] = i4;
                    }
                }

                mat1[l, 1] = sumSq - (sum * sum) / w;
                mat2[l, 1] = 1;
            }

            var starts = new int[classes + 1];
            starts[classes] = mat2[n, classes];
            for (var j = classes - 1; j >= 1; j--)
                starts[j] = mat2[starts[j + 1] - 1, j];

            var bounds = new double[classes];
            for (var j = 1; j < classes; j++)
                bounds[j - 1] = v[Math.Max(0, starts[j + 1] - 1)];
            bounds[classes - 1] = v[v.Count - 1];

            for (var i = 1; i < classes; i++)
                if (bounds[i] <= bounds[i - 1]) bounds[i] = NextBreak(bounds[i - 1]);
            return bounds;
        }

        /// <summary>
        /// 取调色板：colors[] 给的色标按级数重采样；不给就用 ColorBrewer 的 YlOrRd 顺序色阶
        /// （低值浅、高值深 —— 顺序型数据用明度主导的顺序色阶，单色相或多色相均可，不能用彩虹色）。
        /// 8 级以上必须由调用方给足显式色标，避免默认 5 色锚点插值后相邻级分不开。
        /// </summary>
        private static List<CIMColor> ReadPalette(JsonElement args, int classes)
        {
            var hexes = new List<string>();
            if (args.ValueKind == JsonValueKind.Object && args.TryGetProperty("colors", out var arr)
                && arr.ValueKind == JsonValueKind.Array)
                hexes.AddRange(arr.EnumerateArray().Select(e => e.GetString()));

            if (hexes.Count == 0)
                hexes = classes switch
                {
                    3 => new List<string> { "#FFEDA0", "#FEB24C", "#F03B20" },
                    4 => new List<string> { "#FFFFB2", "#FECC5C", "#FD8D3C", "#E31A1C" },
                    5 => new List<string> { "#FFFFB2", "#FECC5C", "#FD8D3C", "#F03B20", "#BD0026" },
                    6 => new List<string> { "#FFFFB2", "#FED976", "#FEB24C", "#FD8D3C", "#FC4E2A", "#B10026" },
                    7 => new List<string> { "#FFFFB2", "#FED976", "#FEB24C", "#FD8D3C", "#FC4E2A", "#E31A1C", "#B10026" },
                    _ => new List<string> { "#FFFFCC", "#FED976", "#FD8D3C", "#E31A1C", "#800026" }
                };

            var rgb = hexes.Select(h => (CIMRGBColor)ParseColor(h)).ToList();
            if (rgb.Count == classes) return rgb.Cast<CIMColor>().ToList();
            if (rgb.Count == 1) return Enumerable.Repeat((CIMColor)rgb[0], classes).ToList();

            // 线性重采样：把 m 个色标拉成 classes 级
            var outp = new List<CIMColor>();
            for (var i = 0; i < classes; i++)
            {
                var t = classes == 1 ? 0.0 : i * (rgb.Count - 1.0) / (classes - 1.0);
                var lo = (int)Math.Floor(t);
                var hi = Math.Min(rgb.Count - 1, lo + 1);
                var f = t - lo;
                var a = rgb[lo];
                var b = rgb[hi];
                outp.Add(new CIMRGBColor
                {
                    R = (int)Math.Round(a.R + (b.R - a.R) * f),
                    G = (int)Math.Round(a.G + (b.G - a.G) * f),
                    B = (int)Math.Round(a.B + (b.B - a.B) * f),
                    Alpha = 100
                });
            }
            return outp;
        }

        /// <summary>
        /// 版式要素：比例尺 / 指北针 / 图例，都挂在同一个地图框上，坐标单位是页面毫米。
        /// 出处：ArcGIS Pro SDK 3.x 文档 ElementFactory.CreateMapSurroundElement 配
        /// ScaleBarInfo / NorthArrowInfo / LegendInfo。
        /// </summary>
        private static object DrawMetricScaleBar(Layout layout, MapFrame frame, JsonElement args)
        {
            var x0 = OptNum(args, "scale_x", 18);
            var y0 = OptNum(args, "scale_y", 9);
            var barMm = OptNum(args, "scale_width", 40);
            var barH = OptNum(args, "scale_height", 1.6);
            var segs = (int)OptNum(args, "scale_divisions", 4);

            var scaleDenom = frame.Camera?.Scale ?? 0;
            if (scaleDenom <= 0) throw new InvalidOperationException("map frame has no scale");

            var metersPerMm = scaleDenom / 1000.0;
            var meterPerSeg = NiceNumber(barMm * metersPerMm / segs);
            var segMm = meterPerSeg / metersPerMm;
            var totalMm = segMm * segs;

            var useKm = meterPerSeg * segs >= 1000;
            var unit = useKm ? "km" : "m";
            Func<double, string> fmt = v => useKm ? (v / 1000.0).ToString("0.###") : v.ToString("0");

            var black = new CIMRGBColor { R = 0, G = 0, B = 0, Alpha = 100 };
            var white = new CIMRGBColor { R = 255, G = 255, B = 255, Alpha = 100 };
            var lineColor = new CIMRGBColor { R = 40, G = 40, B = 40, Alpha = 100 };

            for (var i = 0; i < segs; i++)
            {
                var x = x0 + i * segMm;
                var env = EnvelopeBuilderEx.CreateEnvelope(x, y0, x + segMm, y0 + barH);
                var fill = i % 2 == 0 ? black : white;
                var sym = new CIMPolygonSymbol
                {
                    SymbolLayers = new CIMSymbolLayer[]
                    {
                        new CIMSolidFill { Color = fill },
                        new CIMSolidStroke { Color = lineColor, Width = 0.3f }
                    }
                };
                ElementFactory.Instance.CreateGraphicElement(
                    layout, env, sym, UniqueName(layout, "pb_sb_seg"), false, null);
            }

            var labelSym = SymbolFactory.Instance.ConstructTextSymbol(
                ColorFactory.Instance.BlackRGB, 7, "Microsoft YaHei", "Regular");

            for (var i = 0; i <= segs; i++)
            {
                var x = x0 + i * segMm;
                var text = fmt(meterPerSeg * i) + (i == segs ? " " + unit : "");
                var pt = MapPointBuilderEx.CreateMapPoint(x, y0 + barH + 1.2);
                ElementFactory.Instance.CreateTextGraphicElement(
                    layout, TextType.PointText, pt, labelSym, text, UniqueName(layout, "pb_sb_txt"), false, null);
            }

            return new
            {
                type = "scale_bar",
                name = "pb_scalebar",
                style = "metric-custom",
                meters_per_segment = meterPerSeg,
                segments = segs,
                width_mm = totalMm,
                unit
            };
        }

        private static double NiceNumber(double v)
        {
            if (v <= 0) return 1;
            var exp = Math.Floor(Math.Log10(v));
            var pow = Math.Pow(10, exp);
            var f = v / pow;
            var nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
            return nice * pow;
        }
        private static object AddSurrounds(JsonElement args)
        {
            var layout = GetLayout(args);
            var frame = FindMapFrame(layout, args);
            var page = layout.GetPage();
            var pw = page.Width;
            var ph = page.Height;

            var styles = Project.Current.GetItems<StyleProjectItem>().ToList();
            var style2d = styles.FirstOrDefault(s => s.Name == "ArcGIS 2D") ?? styles.FirstOrDefault();

            var added = new List<object>();

            if (OptFlag(args, "scale_bar", true))
            {
                var sb = DrawMetricScaleBar(layout, frame, args);
                added.Add(sb);
            }

            if (OptFlag(args, "north_arrow", true))
            {
                var want = Optional(args, "arrow_style") ?? "ArcGIS North 10";
                var naStyle = FindNorthArrowStyle(style2d, want);
                var info = new NorthArrowInfo { MapFrameName = frame.Name, NorthArrowStyleItem = naStyle };
                var at = MapPointBuilderEx.CreateMapPoint(
                    OptNum(args, "arrow_x", pw - 24), OptNum(args, "arrow_y", 10));
                var arrow = ElementFactory.Instance.CreateMapSurroundElement(
                    layout, at, info, UniqueName(layout, "pb_northarrow")) as NorthArrow;
                if (arrow != null)
                {
                    arrow.SetHeight(OptNum(args, "arrow_height", 16));
                    added.Add(new { type = "north_arrow", name = arrow.Name, style = naStyle?.Name });
                }
            }

            if (OptFlag(args, "legend", true))
            {
                var x = OptNum(args, "legend_x", pw - 80);
                var y = OptNum(args, "legend_y", 30);
                var w = OptNum(args, "legend_w", 62);
                var h = OptNum(args, "legend_h", 90);
                var env = EnvelopeBuilderEx.CreateEnvelope(x, y, x + w, y + h);
                var info = new LegendInfo { MapFrameName = frame.Name };
                var legend = ElementFactory.Instance.CreateMapSurroundElement(
                    layout, env, info, UniqueName(layout, "pb_legend")) as Legend;
                if (legend != null)
                {
                    PolishLegend(legend, args);
                    added.Add(new { type = "legend", name = legend.Name, x, y, w, h });
                }
            }

            return new { layout = layout.Name, frame = frame.Name, page = new[] { pw, ph }, added };
        }

        /// <summary>
        /// 比例尺单位：CIM 里 units 是枚举，但 pro sdk 没暴露可赋值的公开类型，
        /// 所以走 CIM 的 JSON 往返只替换 units 字段（默认 km，国内专题图不用英里）。
        /// </summary>
        private static string ApplyScaleBarUnits(ScaleBar bar, JsonElement args)
        {
            var want = (Optional(args, "scale_units") ?? "km").ToLowerInvariant();
            var esri = want switch
            {
                "m" => "esriMeters",
                "mi" => "esriMiles",
                "ft" => "esriFeet",
                "yd" => "esriYards",
                "nmi" => "esriNauticalMiles",
                _ => "esriKilometers"
            };
            string json;
            try
            {
                json = bar.GetDefinition().ToJson();
            }
            catch (Exception ex)
            {
                return "no-definition: " + ex.Message;
            }

            var patched = System.Text.RegularExpressions.Regex.Replace(  // 已存在则改，不存在则下面插入
                json, "\"units\"\\s*:\\s*\"[^\"]*\"", "\"units\":\"" + esri + "\"");
            // CIM 序列化会省略默认值，esriMiles 是默认值所以 json 里根本没有 units 字段，
            // 正则替换无效时直接把 units 插到对象开头。
            var injected = patched != json
                ? patched
                : "{\"units\":\"" + esri + "\"," + json.Substring(1).TrimStart();
            try
            {
                bar.SetDefinition((CIMElement)(object)CIMScaleBar.FromJson(injected));
                return "units=" + esri;
            }
            catch (Exception ex)
            {
                return "error: " + ex.GetType().Name + ": " + ex.Message;
            }
        }

        /// <summary>
        /// 图例排版：默认图例的图层名/字段名用的是大号字，出图会盖住地图。
        /// 这里统一压到 6~7pt，并关掉分级设色的字段名标题（ClassBreaks 会把字段名
        /// 当 Heading 显示，如 BUI_PCT），图例只留「图层名 + 各级色块 + 区间」。
        /// </summary>
        private static void PolishLegend(Legend legend, JsonElement args)
        {
            try
            {
                if (!(legend.GetDefinition() is CIMLegend lg)) return;

                var labelSize = OptNum(args, "legend_font", 7);
                var nameSize = OptNum(args, "legend_name_font", 7.5);
                var labelSym = SymRef(labelSize);
                var nameSym = SymRef(nameSize);
                var smallSym = SymRef(Math.Max(5, labelSize - 1));
                var titleSym = SymRef(OptNum(args, "legend_title_font", 9));

                lg.ShowTitle = OptFlag(args, "legend_title", false);
                lg.TitleSymbol = titleSym;

                if (lg.Items != null)
                {
                    foreach (var item in lg.Items)
                    {
                        if (item == null) continue;
                        item.ShowHeading = false;
                        item.ShowDescription = false;
                        item.LabelSymbol = labelSym;
                        item.HeadingSymbol = smallSym;
                        item.LayerNameSymbol = nameSym;
                        item.DescriptionSymbol = smallSym;
                        if (item.PatchHeight > 4) item.PatchHeight = 3.2;
                        if (item.PatchWidth > 10) item.PatchWidth = 7.5;
                    }
                }

                legend.SetDefinition((CIMElement)(object)lg);
            }
            catch
            {
            }
        }

        private static CIMSymbolReference SymRef(double size)
        {
            return new CIMSymbolReference { Symbol = SymbolFactory.Instance.ConstructTextSymbol(
                ColorFactory.Instance.BlackRGB, size, "Microsoft YaHei", "Regular") };
        }

        private static MapFrame FindMapFrame(Layout layout, JsonElement args)        {
            var wanted = Optional(args, "frame");
            var frames = layout.GetElementsAsFlattenedList().OfType<MapFrame>().ToList();
            if (frames.Count == 0) throw new InvalidOperationException("layout has no map frame");
            if (string.IsNullOrEmpty(wanted)) return frames[0];
            return frames.FirstOrDefault(f => f.Name == wanted)
                   ?? throw new InvalidOperationException($"map frame not found: {wanted}");
        }

        private static string UniqueName(Layout layout, string stem)
        {
            var taken = new HashSet<string>(layout.GetElementsAsFlattenedList().Select(e => e.Name));
            if (!taken.Contains(stem)) return stem;
            for (var i = 2; i < 100; i++)
            {
                var candidate = stem + "_" + i;
                if (!taken.Contains(candidate)) return candidate;
            }
            return stem;
        }

        private static ScaleBarStyleItem FindScaleBarStyle(StyleProjectItem style, string name)
        {
            if (style == null) return null;
            try
            {
                var items = style.SearchScaleBars(name);
                if (items.Count > 0) return items[0];
                var all = style.SearchScaleBars(string.Empty);
                return all.Count > 0 ? all[0] : null;
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static NorthArrowStyleItem FindNorthArrowStyle(StyleProjectItem style, string name)
        {
            if (style == null) return null;
            try
            {
                var items = style.SearchNorthArrows(name);
                if (items.Count > 0) return items[0];
                var all = style.SearchNorthArrows(string.Empty);
                return all.Count > 0 ? all[0] : null;
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>
        /// opacity is 0..100 (100 = fully opaque). The API takes the inverse (transparency),
        /// so a shapefile hillshade at opacity 45 becomes SetTransparency(55).
        /// </summary>
        private static void ApplyOpacity(Layer layer, JsonElement args)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty("opacity", out var v)) return;
            if (v.ValueKind == JsonValueKind.Null) return;

            var opacity = v.GetDouble();
            layer.SetTransparency(Math.Max(0.0, Math.Min(100.0, 100.0 - opacity)));
        }

        private static int CountColors(JsonElement args)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty("colors", out var arr)
                || arr.ValueKind != JsonValueKind.Array) return 0;
            return arr.GetArrayLength();
        }

        /// <summary>
        /// Builds a colour ramp from a hex list. Two stops become one linear ramp; more stops are
        /// strung together as equal-weight linear segments (CIMMultipartColorRamp), which is how
        /// ArcGIS stores a hand-edited hypsometric ramp.
        /// </summary>
        private static CIMColorRamp BuildColorRamp(JsonElement args)
        {
            if (CountColors(args) == 0) return null;   // keep the layer's own ramp

            var colors = args.GetProperty("colors").EnumerateArray()
                             .Select(e => ParseColor(e.GetString()))
                             .ToList();

            if (colors.Count < 2)
                throw new InvalidOperationException("colors needs at least 2 entries (#RRGGBB)");

            if (colors.Count == 2)
                return new CIMLinearContinuousColorRamp { FromColor = colors[0], ToColor = colors[1] };

            var segments = new List<CIMColorRamp>();
            for (var i = 0; i + 1 < colors.Count; i++)
                segments.Add(new CIMLinearContinuousColorRamp { FromColor = colors[i], ToColor = colors[i + 1] });

            return new CIMMultipartColorRamp
            {
                ColorRamps = segments.ToArray(),
                Weights = Enumerable.Repeat(1.0, segments.Count).ToArray()
            };
        }

        private static CIMColor ParseColor(string hex)
        {
            if (string.IsNullOrWhiteSpace(hex))
                throw new InvalidOperationException("empty colour; use #RRGGBB");

            var s = hex.Trim().TrimStart('#');
            if (s.Length == 3) s = string.Concat(s.Select(ch => new string(ch, 2)));
            if (s.Length != 6)
                throw new InvalidOperationException($"bad colour: {hex} (expected #RRGGBB)");

            return new CIMRGBColor
            {
                R = Convert.ToInt32(s.Substring(0, 2), 16),
                G = Convert.ToInt32(s.Substring(2, 2), 16),
                B = Convert.ToInt32(s.Substring(4, 2), 16),
                Alpha = 100
            };
        }

        private static CIMSymbol BuildFeatureSymbol(esriGeometryType shape, JsonElement args)
        {
            var fillHex = Optional(args, "fill") ?? "none";
            var fillAlpha = OptNum(args, "fill_alpha", 100);
            var outlineHex = Optional(args, "outline") ?? "#3F3F3F";
            var width = OptNum(args, "width", 1.0);

            var stroke = new CIMSolidStroke { Color = ParseColor(outlineHex), Width = (float)width };

            if (shape == esriGeometryType.esriGeometryPolyline || shape == esriGeometryType.esriGeometryLine)
                return new CIMLineSymbol { SymbolLayers = new CIMSymbolLayer[] { stroke } };

            if (shape == esriGeometryType.esriGeometryPoint || shape == esriGeometryType.esriGeometryMultipoint)
            {
                var pointFillHex = Optional(args, "fill") ?? "#D73027";
                var size = OptNum(args, "size", 8.0);
                var markerName = (Optional(args, "marker") ?? "circle").ToLowerInvariant();
                var pointFill = (CIMRGBColor)ParseColor(pointFillHex);
                pointFill.Alpha = (float)fillAlpha;
                var point = (CIMPointSymbol)SymbolFactory.Instance.ConstructPointSymbol(
                    pointFill, size, ParseMarkerStyle(markerName));

                var haloHex = Optional(args, "halo") ?? "#FFFFFF";
                var haloSize = OptNum(args, "halo_size", Math.Max(0.6, size * 0.12));
                if (!haloHex.Equals("none", StringComparison.OrdinalIgnoreCase))
                {
                    point.HaloSymbol = new CIMPolygonSymbol
                    {
                        SymbolLayers = new CIMSymbolLayer[]
                        {
                            new CIMSolidFill { Color = ParseColor(haloHex) }
                        }
                    };
                    point.HaloSize = haloSize;
                }
                return point;
            }

            CIMColor fill;
            if (fillHex.Equals("none", StringComparison.OrdinalIgnoreCase))
            {
                fill = new CIMRGBColor { R = 0, G = 0, B = 0, Alpha = 0 };   // hollow: 空心描边
            }
            else
            {
                var c = (CIMRGBColor)ParseColor(fillHex);
                c.Alpha = (float)fillAlpha;
                fill = c;
            }

            return new CIMPolygonSymbol
            {
                SymbolLayers = new CIMSymbolLayer[] { stroke, new CIMSolidFill { Color = fill } }
            };
        }

        private static object CreateMap(JsonElement args)
        {
            var name = Require(args, "name");
            var existing = Project.Current.GetItems<MapProjectItem>().FirstOrDefault(i => i.Name == name);
            if (existing != null) return new { map = name, created = false };

            var map = MapFactory.Instance.CreateMap(name, MapType.Map, MapViewingMode.Map, default(Basemap));
            return new { map = map.Name, created = true };
        }

        /// <summary>
        /// Builds a multi-panel layout from scratch: one map frame per entry in
        /// `frames`, plus a caption under each. Coordinates are millimetres from
        /// the page's lower-left corner.
        /// </summary>
        private static object CreatePanelLayout(JsonElement args)
        {
            var name = Require(args, "name");
            var pageW = Num(args, "page_w");
            var pageH = Num(args, "page_h");

            if (Project.Current.GetItems<LayoutProjectItem>().Any(i => i.Name == name))
                throw new InvalidOperationException($"layout already exists: {name}");

            var layout = LayoutFactory.Instance.CreateLayout(pageW, pageH, LinearUnit.Millimeters, false, 0.5)
                         ?? throw new InvalidOperationException("CreateLayout returned null");
            layout.SetName(name);

            if (!args.TryGetProperty("frames", out var frames) || frames.ValueKind != JsonValueKind.Array)
                throw new InvalidOperationException("missing arg: frames");

            var created = new List<object>();
            foreach (var f in frames.EnumerateArray())
            {
                var frameName = f.GetProperty("name").GetString();
                var mapName = f.GetProperty("map").GetString();
                double x = f.GetProperty("x").GetDouble();
                double y = f.GetProperty("y").GetDouble();
                double w = f.GetProperty("w").GetDouble();
                double h = f.GetProperty("h").GetDouble();

                var map = Project.Current.GetItems<MapProjectItem>()
                              .FirstOrDefault(i => i.Name == mapName)?.GetMap()
                          ?? throw new InvalidOperationException($"map not found: {mapName}");

                var env = EnvelopeBuilderEx.CreateEnvelope(x, y, x + w, y + h);
                var frame = ElementFactory.Instance.CreateMapFrameElement(layout, env, map, frameName, false, null);

                if (f.TryGetProperty("title", out var title) && title.ValueKind == JsonValueKind.String)
                    AddText(layout, frameName + "_caption", title.GetString(), x + 1, y + h + 2, 8, true);

                created.Add(new { frame = frame.Name, map = mapName, x, y, w, h });
            }

            return new { layout = name, page = new[] { pageW, pageH }, frames = created };
        }

        private static void AddText(Layout layout, string name, string text, double x, double y,
                                    double size, bool bold)
        {
            var symbol = SymbolFactory.Instance.ConstructTextSymbol(
                ColorFactory.Instance.BlackRGB, size, "Microsoft YaHei", bold ? "Bold" : "Regular");

            var graphic = new CIMTextGraphic
            {
                Text = text,
                Symbol = new CIMSymbolReference { Symbol = symbol },
                Shape = MapPointBuilderEx.CreateMapPoint(x, y)
            };

            ElementFactory.Instance.CreateGraphicElement(layout, graphic, name, false, null);
        }

        private static object ExportLayout(JsonElement args)
        {
            var layout = GetLayout(args);
            var path = Path.GetFullPath(Require(args, "path"));
            var dpi = args.ValueKind == JsonValueKind.Object && args.TryGetProperty("dpi", out var d)
                ? d.GetInt32()
                : 300;
            var format = (Optional(args, "format") ?? "png").ToLowerInvariant();

            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            ExportFormat fmt;
            switch (format)
            {
                case "png":
                    fmt = new PNGFormat { Resolution = dpi, OutputFileName = path };
                    break;
                case "jpg":
                case "jpeg":
                    fmt = new JPEGFormat { Resolution = dpi, OutputFileName = path };
                    break;
                case "tif":
                case "tiff":
                    fmt = new TIFFFormat { Resolution = dpi, OutputFileName = path };
                    break;
                case "pdf":
                    fmt = new PDFFormat { Resolution = dpi, OutputFileName = path };
                    break;
                default:
                    throw new InvalidOperationException($"unsupported format: {format} (png/jpg/tiff/pdf)");
            }

            layout.Export(fmt);
            return new { path, format, dpi, bytes = new FileInfo(path).Length };
        }

        private static Layout GetLayout(JsonElement args)
        {
            // export_layout historically used "name"; everything else uses "layout".
            var name = Optional(args, "layout") ?? Optional(args, "name")
                       ?? throw new InvalidOperationException("missing arg: layout");
            return Project.Current.GetItems<LayoutProjectItem>()
                       .FirstOrDefault(i => i.Name == name)?.GetLayout()
                   ?? throw new InvalidOperationException($"layout not found: {name}");
        }

        /// <summary>
        /// Lists what a layout is made of, so an agent can find the title element
        /// before calling set_text.
        /// </summary>
        private static object ListElements(JsonElement args)
        {
            var layout = GetLayout(args);
            return layout.GetElementsAsFlattenedList()
                .Select(e =>
                {
                    var row = new Dictionary<string, object>
                    {
                        ["name"] = e.Name,
                        ["type"] = e.GetType().Name,
                        ["visible"] = e.IsVisible
                    };
                    if (e is TextElement text)
                        row["text"] = Clip(text.TextProperties?.Text, 120);
                    if (e is MapFrame frame)
                        row["map"] = frame.Map?.Name;
                    return row;
                })
                .ToArray();
        }

        /// <summary>
        /// Replaces the text of a text element. Identify the element by name, or by
        /// its index among text elements (0 = first, usually the title).
        /// </summary>
        private static object SetText(JsonElement args)
        {
            var layout = GetLayout(args);
            var value = Require(args, "text");
            var name = Optional(args, "name");

            var texts = layout.GetElementsAsFlattenedList().OfType<TextElement>().ToList();
            if (texts.Count == 0) throw new InvalidOperationException("layout has no text element");

            TextElement target;
            if (name != null)
            {
                target = texts.FirstOrDefault(t => t.Name == name)
                         ?? throw new InvalidOperationException(
                             $"text element not found: {name} (have: {string.Join(", ", texts.Select(t => t.Name))})");
            }
            else
            {
                var index = 0;
                if (args.ValueKind == JsonValueKind.Object && args.TryGetProperty("index", out var i))
                    index = i.GetInt32();
                if (index < 0 || index >= texts.Count)
                    throw new InvalidOperationException($"text index out of range: {index} (layout has {texts.Count})");
                target = texts[index];
            }

            var props = target.TextProperties;
            var before = props.Text;
            props.Text = value;
            target.SetTextProperties(props);

            return new { name = target.Name, before = Clip(before, 120), text = value };
        }

        /// <summary>
        /// Shows or hides one element. A4_Landscape.pagx ships two scale bars
        /// (mi and km); hiding one is how you get a single-unit scale.
        /// </summary>
        private static object SetVisible(JsonElement args)
        {
            var layout = GetLayout(args);
            var name = Require(args, "name");
            var visible = !(args.ValueKind == JsonValueKind.Object
                            && args.TryGetProperty("visible", out var v)
                            && v.ValueKind == JsonValueKind.False);

            var element = layout.GetElementsAsFlattenedList().FirstOrDefault(e => e.Name == name)
                          ?? throw new InvalidOperationException($"element not found: {name}");
            element.SetVisible(visible);
            return new { name, visible };
        }

        /// <summary>
        /// Run any geoprocessing tool in the live session. `params` are positional
        /// values in the tool's parameter order, e.g.
        /// ["D:/in.shp", "D:/out.shp", "1000 Meters"] for analysis.Buffer.
        /// GPExecuteToolFlags.AddOutputsToMap puts the result in the active map.
        /// </summary>
        private static async Task<object> RunGpAsync(JsonElement args)
        {
            var tool = Require(args, "tool");
            var values = new List<object>();
            if (args.ValueKind == JsonValueKind.Object
                && args.TryGetProperty("params", out var p)
                && p.ValueKind == JsonValueKind.Array)
            {
                foreach (var el in p.EnumerateArray())
                    values.Add(ToGpValue(el));
            }

            // Remember which string parameters already exist before the tool runs,
            // so the fallback below never mistakes an input dataset for an output.
            var inputPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var value in values.OfType<string>())
            {
                try
                {
                    var full = Path.GetFullPath(value);
                    if (File.Exists(full) || Directory.Exists(full)) inputPaths.Add(full);
                }
                catch { /* not a path */ }
            }

            var overwrite = OptFlag(args, "overwrite", false);
            var timeoutS = OptNum(args, "timeout_s", 0);
            var valueArray = Geoprocessing.MakeValueArray(values.ToArray());
            var environments = Geoprocessing.MakeEnvironmentArray(overwriteoutput: overwrite);

            using var cts = new CancellationTokenSource();
            if (timeoutS > 0) cts.CancelAfter(TimeSpan.FromSeconds(timeoutS));

            IGPResult gpResult;
            try
            {
                gpResult = await Geoprocessing.ExecuteToolAsync(
                    tool, valueArray, environments,
                    cts.Token,
                    (GPToolExecuteEventHandler)null,
                    GPExecuteToolFlags.AddOutputsToMap);
            }
            catch (OperationCanceledException)
            {
                return new
                {
                    tool,
                    succeeded = false,
                    cancelled = true,
                    timeout_s = timeoutS,
                    overwrite,
                    outputs = (object)null,
                    addedToMap = Array.Empty<string>(),
                    warnings = new[] { timeoutS > 0
                        ? $"geoprocessing cancelled after {timeoutS:0.###} s"
                        : "geoprocessing cancelled" },
                    messages = Array.Empty<string>(),
                    errorMessages = new[] { "cancelled" },
                };
            }

            // AddOutputsToMap normally does the job, but the first GP run right
            // after a map pane is created can return before the pane is ready and
            // silently skip it. Check what actually landed on the map, and add
            // missing layer outputs ourselves.
            var outputs = gpResult.Values == null
                ? new List<string>()
                : gpResult.Values.OfType<string>()
                    .Where(v => !string.IsNullOrWhiteSpace(v)).ToList();
            var added = new List<string>();
            var warnings = new List<string>();
            var wasCancelled = cts.IsCancellationRequested && gpResult.IsFailed;
            if (wasCancelled)
                warnings.Add($"geoprocessing cancelled after {timeoutS:0.###} s");

            try
            {
                var map = await QueuedTask.Run(() => GetMap(args));
                var existing = await QueuedTask.Run(() =>
                    new HashSet<string>(
                        map.Layers.Select(l => l.Name), StringComparer.OrdinalIgnoreCase));

                foreach (var raw in outputs)
                {
                    var path = Path.GetFullPath(raw);
                    var file = Path.GetFileName(path);
                    var name = Path.GetFileNameWithoutExtension(path);
                    if (string.IsNullOrEmpty(name)
                        || existing.Contains(name)
                        || existing.Contains(file)
                        || inputPaths.Contains(path)) continue;

                    var isDataset = File.Exists(path) || Directory.Exists(path)
                        || path.IndexOf(".gdb", StringComparison.OrdinalIgnoreCase) >= 0;
                    if (!isDataset) continue;

                    try
                    {
                        var layer = await QueuedTask.Run(() =>
                            LayerFactory.Instance.CreateLayer(new Uri(path), map, 0, name));
                        if (layer != null)
                        {
                            added.Add(layer.Name);
                            existing.Add(layer.Name);
                        }
                    }
                    catch (Exception ex)
                    {
                        // Tables and memory workspaces are not layer sources.
                        warnings.Add($"{name}: {ex.Message}");
                    }
                }
            }
            catch (Exception ex)
            {
                warnings.Add("could not add outputs: " + ex.Message);
            }

            return new
            {
                tool,
                succeeded = !gpResult.IsFailed,
                cancelled = wasCancelled,
                timeout_s = timeoutS,
                overwrite,
                errorCode = gpResult.ErrorCode,
                returnValue = gpResult.ReturnValue,
                outputs = gpResult.Values,
                addedToMap = added,
                warnings,
                messages = gpResult.Messages?.Select(m => m.Text).ToArray(),
                errorMessages = gpResult.ErrorMessages?.Select(m => m.Text).ToArray(),
            };
        }

        private static object ToGpValue(JsonElement el)
        {
            switch (el.ValueKind)
            {
                case JsonValueKind.Null: return null;
                case JsonValueKind.True: return true;
                case JsonValueKind.False: return false;
                case JsonValueKind.Number:
                    return el.TryGetInt64(out var integer) ? (object)integer : el.GetDouble();
                case JsonValueKind.String:
                    return el.GetString();
                case JsonValueKind.Array:
                    return el.EnumerateArray().Select(ToGpValue).ToArray();
                default:
                    return el.GetRawText();
            }
        }

        private static string Clip(string s, int max)
        {
            if (string.IsNullOrEmpty(s)) return s;
            s = s.Replace("\r", " ").Replace("\n", " ");
            return s.Length <= max ? s : s.Substring(0, max) + "…";
        }

        private static Map GetMap(JsonElement args)
        {
            var name = Optional(args, "map");
            if (name != null)
            {
                var named = Project.Current.GetItems<MapProjectItem>().FirstOrDefault(i => i.Name == name);
                return named?.GetMap() ?? throw new InvalidOperationException($"map not found: {name}");
            }

            var active = MapView.Active?.Map;
            if (active != null) return active;

            // A layout pane may be in front, which nulls MapView.Active. Fall back to the
            // project's first map so layer commands keep working while a layout is open.
            var first = Project.Current.GetItems<MapProjectItem>().FirstOrDefault();
            return first?.GetMap() ?? throw new InvalidOperationException("no map in project");
        }

        private static IEnumerable<Layer> EnumerateLayers(IEnumerable<Layer> layers)
        {
            foreach (var layer in layers)
            {
                yield return layer;
                if (layer is GroupLayer group)
                {
                    foreach (var child in EnumerateLayers(group.Layers))
                        yield return child;
                }
            }
        }

        private static (Layer Layer, GroupLayer Parent) FindLayerWithParent(
            IEnumerable<Layer> layers, string name, GroupLayer parent = null)
        {
            foreach (var layer in layers)
            {
                if (layer.Name == name) return (layer, parent);
                if (layer is GroupLayer group)
                {
                    var found = FindLayerWithParent(group.Layers, name, group);
                    if (found.Layer != null) return found;
                }
            }
            return (null, null);
        }

        private static void CollectLayers(
            IEnumerable<Layer> layers, string prefix, GroupLayer parent,
            List<(Layer Layer, GroupLayer Parent)> targets)
        {
            foreach (var layer in layers)
            {
                if (layer.Name.StartsWith(prefix, StringComparison.Ordinal))
                {
                    targets.Add((layer, parent));
                    continue;
                }
                if (layer is GroupLayer group)
                    CollectLayers(group.Layers, prefix, group, targets);
            }
        }

        private static Layer FindLayer(JsonElement args)
        {
            var map = GetMap(args);
            var name = Require(args, "layer");
            return EnumerateLayers(map.Layers).FirstOrDefault(l => l.Name == name)
                   ?? throw new InvalidOperationException($"layer not found: {name}");
        }

        private static string Require(JsonElement args, string key)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(key, out var v))
                throw new InvalidOperationException($"missing arg: {key}");
            return v.GetString();
        }

        private static string Optional(JsonElement args, string key)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(key, out var v)) return null;
            return v.ValueKind == JsonValueKind.Null ? null : v.GetString();
        }

        private static double Num(JsonElement args, string key)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(key, out var v))
                throw new InvalidOperationException($"missing arg: {key}");
            return v.GetDouble();
        }

        private static double OptNum(JsonElement args, string key, double fallback)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(key, out var v)) return fallback;
            if (v.ValueKind == JsonValueKind.Null) return fallback;
            return v.GetDouble();
        }

        private static bool OptFlag(JsonElement args, string key, bool fallback)
        {
            if (args.ValueKind != JsonValueKind.Object || !args.TryGetProperty(key, out var v)) return fallback;
            if (v.ValueKind == JsonValueKind.Null) return fallback;
            if (v.ValueKind == JsonValueKind.True) return true;
            if (v.ValueKind == JsonValueKind.False) return false;
            return bool.TryParse(v.ToString(), out var b) && b;
        }

        private static Task<object> OnUIAsync(Func<Task<object>> fn)
        {
            var tcs = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
            Application.Current.Dispatcher.Invoke(() => { _ = CompleteAsync(fn, tcs); });
            return tcs.Task;
        }

        private static async Task CompleteAsync(Func<Task<object>> fn, TaskCompletionSource<object> tcs)
        {
            try
            {
                tcs.SetResult(await fn());
            }
            catch (Exception ex)
            {
                tcs.SetException(ex);
            }
        }
    }
}
