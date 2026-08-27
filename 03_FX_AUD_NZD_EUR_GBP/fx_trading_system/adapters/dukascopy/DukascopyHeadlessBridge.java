package adapters.dukascopy;

import com.dukascopy.api.system.ClientFactory;
import com.dukascopy.api.system.IClient;
import com.dukascopy.api.system.ISystemListener;

import java.io.File;

/**
 * 无头桥启动器：用高层 ClientFactory/IClient API 连接 Dukascopy demo，
 * 连接成功后启动 DukascopyBridgeStrategy（把行情转发给 Python 后端 + 执行信号）。
 *
 * 环境变量（来自 .env.dukascopy_demo.local）：
 *   DUKASCOPY_DEMO_JNLP_URL / DUKASCOPY_DEMO_USER / DUKASCOPY_DEMO_PASSWORD
 *   DUKASCOPY_BACKEND_URL（可选，默认 http://localhost:8001）
 */
public class DukascopyHeadlessBridge {

    public static void main(String[] args) throws Exception {
        String jnlpUrl = System.getenv("DUKASCOPY_DEMO_JNLP_URL");
        String user = System.getenv("DUKASCOPY_DEMO_USER");
        String password = System.getenv("DUKASCOPY_DEMO_PASSWORD");
        String backendUrlEnv = System.getenv("DUKASCOPY_BACKEND_URL");
        final String backendUrl = (backendUrlEnv != null && !backendUrlEnv.isBlank())
                ? backendUrlEnv
                : "http://localhost:8001";

        if (jnlpUrl == null || jnlpUrl.isBlank()
                || user == null || user.isBlank()
                || password == null || password.isBlank()) {
            System.err.println("[bridge] 缺少 DUKASCOPY_DEMO_JNLP_URL / USER / PASSWORD");
            System.exit(2);
        }

        final IClient client = ClientFactory.getDefaultInstance();
        // 关键：headless 模式需要显式指定缓存目录（否则品种元数据/系统设置服务 bEv() 为 null，订阅行情时 NPE）
        File cacheDir = new File(System.getProperty("user.home"), "Library/Application Support/JForex");
        cacheDir.mkdirs();
        client.setCacheDirectory(cacheDir);
        client.setSystemListener(new ISystemListener() {
            @Override
            public void onStart(long processId) {
            }

            @Override
            public void onStop(long processId) {
                System.out.println("[bridge] platform stopped, exiting.");
                System.exit(0);
            }

            @Override
            public void onConnect() {
                System.out.println("[bridge] connected.");
                // 关键：连接后 SDK 还需异步加载品种元数据/系统设置，立即 startStrategy 会撞上 bEv() null。
                // 新开线程等待平台数据就绪后再启动策略。
                new Thread(new Runnable() {
                    @Override
                    public void run() {
                        try {
                            Thread.sleep(10000);
                            DukascopyBridgeStrategy strategy = new DukascopyBridgeStrategy();
                            strategy.backendUrl = backendUrl;
                            client.startStrategy(strategy);
                            System.out.println("[bridge] strategy started.");
                        } catch (Exception e) {
                            System.err.println("[bridge] startStrategy failed:");
                            e.printStackTrace();
                        }
                    }
                }, "bridge-strategy-starter").start();
            }

            @Override
            public void onDisconnect() {
                System.out.println("[bridge] disconnected.");
            }
        });

        System.out.println("[bridge] connecting to Dukascopy demo...");
        client.connect(jnlpUrl, user, password);

        // 常驻：靠上面的 onStop 退出
        Thread.sleep(Long.MAX_VALUE);
    }
}
