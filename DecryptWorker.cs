using System;
using System.Runtime.InteropServices;
using System.Text;
using System.IO;

public class DecryptWorker {
    private static class StdCallCrypto {
        [DllImport("C:\\mts3\\IndvInfmCrypto.dll", EntryPoint = "initialize", CallingConvention = CallingConvention.StdCall)]
        public static extern int initialize(ref IntPtr handle);

        [DllImport("C:\\mts3\\IndvInfmCrypto.dll", EntryPoint = "release", CallingConvention = CallingConvention.StdCall)]
        public static extern void release(ref IntPtr handle);

        [DllImport("C:\\mts3\\IndvInfmCrypto.dll", EntryPoint = "free_memory", CallingConvention = CallingConvention.StdCall)]
        public static extern void free_memory(ref IntPtr ptr);

        [DllImport("C:\\mts3\\IndvInfmCrypto.dll", EntryPoint = "setEncryptionPassword", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
        public static extern int setEncryptionPassword(IntPtr handle, string password);

        [DllImport("C:\\mts3\\IndvInfmCrypto.dll", EntryPoint = "decodeBase64", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
        public static extern int decodeBase64(
            IntPtr handle,
            string base64Data,
            ref IntPtr outBuf,
            ref int outLen
        );

        [DllImport("C:\\mts3\\IndvInfmCrypto.dll", EntryPoint = "decryptDataWithKey", CallingConvention = CallingConvention.StdCall)]
        public static extern int decryptDataWithKey(
            IntPtr handle,
            IntPtr data,
            int dataLen,
            ref IntPtr outBuf,
            ref int outLen
        );
    }

    private static void WriteProtocol(string format, params object[] args) {
        string msg = (args != null && args.Length > 0) ? string.Format(format, args) : format;
        Console.Write("\n" + msg + "\n");
        Console.Out.Flush();
    }

    [System.Runtime.ExceptionServices.HandleProcessCorruptedStateExceptions]
    [System.Security.SecurityCritical]
    public static void Main(string[] args) {
        // Set working directory to C:\mts3 where the DLL and configuration files reside
        try {
            Directory.SetCurrentDirectory("C:\\mts3");
        } catch (Exception ex) {
            WriteProtocol("ERROR: Failed to set working directory: {0}", ex.Message);
            return;
        }

        IntPtr handle = IntPtr.Zero;
        try {
            int initRes = StdCallCrypto.initialize(ref handle);
            if (initRes != 0 || handle == IntPtr.Zero) {
                WriteProtocol("ERROR: initialize failed with code {0}", initRes);
                return;
            }

            string password = "icando00~";
            int passRes = StdCallCrypto.setEncryptionPassword(handle, password);
            if (passRes != 0) {
                WriteProtocol("ERROR: setEncryptionPassword failed with code {0}", passRes);
                StdCallCrypto.release(ref handle);
                return;
            }

            // Signal to the parent process that the worker is initialized and ready
            WriteProtocol("READY");

            // Main IPC loop
            string line;
            while ((line = Console.ReadLine()) != null) {
                line = line.Trim();
                if (string.IsNullOrEmpty(line)) {
                    WriteProtocol("ERROR: Empty input");
                    continue;
                }

                if (line == "PING") {
                    WriteProtocol("PONG");
                    continue;
                }

                IntPtr decBuf = IntPtr.Zero;
                int decLen = 0;
                IntPtr decryptBuf = IntPtr.Zero;
                int decryptLen = 0;

                try {
                    int decodeRes = StdCallCrypto.decodeBase64(handle, line, ref decBuf, ref decLen);
                    if (decodeRes != 0 || decLen <= 0 || decBuf == IntPtr.Zero) {
                        WriteProtocol("ERROR: decodeBase64 failed with code {0}", decodeRes);
                        continue;
                    }

                    int decryptRes = StdCallCrypto.decryptDataWithKey(handle, decBuf, decLen, ref decryptBuf, ref decryptLen);
                    if (decryptRes != 0 || decryptLen <= 0 || decryptBuf == IntPtr.Zero) {
                        WriteProtocol("ERROR: decryptDataWithKey failed with code {0}", decryptRes);
                        continue;
                    }

                    byte[] bytes = new byte[decryptLen];
                    Marshal.Copy(decryptBuf, bytes, 0, decryptLen);
                    // Patient registration numbers (RRN) are plain ASCII string values (YYMMDD-GXXXXXX)
                    string result = Encoding.ASCII.GetString(bytes);
                    WriteProtocol("OK:{0}", result);

                } catch (Exception ex) {
                    WriteProtocol("ERROR: Decryption exception: {0}", ex.Message);
                } finally {
                    if (decBuf != IntPtr.Zero) {
                        StdCallCrypto.free_memory(ref decBuf);
                    }
                    if (decryptBuf != IntPtr.Zero) {
                        StdCallCrypto.free_memory(ref decryptBuf);
                    }
                }
            }
        } catch (Exception ex) {
            WriteProtocol("ERROR: Global exception: {0}", ex.Message);
        } finally {
            if (handle != IntPtr.Zero) {
                StdCallCrypto.release(ref handle);
            }
        }
    }
}
