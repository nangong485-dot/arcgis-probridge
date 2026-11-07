using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace ProBridge
{
    internal sealed class BridgeServer
    {
        private readonly int _port;
        private TcpListener _listener;
        private Thread _acceptThread;
        private volatile bool _running;

        public BridgeServer(int port = 7788)
        {
            _port = port;
        }

        public void Start()
        {
            if (_running) return;
            _listener = new TcpListener(IPAddress.Loopback, _port);
            _listener.Start();
            _running = true;
            _acceptThread = new Thread(AcceptLoop)
            {
                IsBackground = true,
                Name = "ProBridge.Accept"
            };
            _acceptThread.Start();
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { }
        }

        private void AcceptLoop()
        {
            while (_running)
            {
                TcpClient client;
                try
                {
                    client = _listener.AcceptTcpClient();
                }
                catch
                {
                    break;
                }

                _ = Task.Run(() => ServeAsync(client));
            }
        }

        private async Task ServeAsync(TcpClient client)
        {
            using (client)
            using (var stream = client.GetStream())
            using (var reader = new StreamReader(stream, new UTF8Encoding(false)))
            using (var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true })
            {
                string line;
                while ((line = await reader.ReadLineAsync()) != null)
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var response = await HandleLineAsync(line);
                    await writer.WriteLineAsync(response);
                }
            }
        }

        private async Task<string> HandleLineAsync(string line)
        {
            string id = null;
            try
            {
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                if (root.TryGetProperty("id", out var idEl)) id = idEl.GetString();

                var cmd = root.GetProperty("cmd").GetString();
                var args = root.TryGetProperty("args", out var a) ? a.Clone() : default;

                var data = await Handlers.ExecuteAsync(cmd, args);
                return JsonSerializer.Serialize(new { id, ok = true, data });
            }
            catch (Exception ex)
            {
                var msg = ex.InnerException?.Message ?? ex.Message;
                return JsonSerializer.Serialize(new { id, ok = false, error = new { code = "EXCEPTION", msg } });
            }
        }
    }
}
