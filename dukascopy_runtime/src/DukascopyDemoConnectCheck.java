import com.dukascopy.api.system.ClientFactory;
import com.dukascopy.api.system.IClient;
import com.dukascopy.api.system.ISystemListener;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class DukascopyDemoConnectCheck {
    public static void main(String[] args) throws Exception {
        String jnlpUrl = System.getenv("DUKASCOPY_DEMO_JNLP_URL");
        String user = System.getenv("DUKASCOPY_DEMO_USER");
        String password = System.getenv("DUKASCOPY_DEMO_PASSWORD");

        if (jnlpUrl == null || jnlpUrl.isBlank()) {
            throw new IllegalStateException("Missing DUKASCOPY_DEMO_JNLP_URL");
        }
        if (user == null || user.isBlank()) {
            throw new IllegalStateException("Missing DUKASCOPY_DEMO_USER");
        }
        if (password == null || password.isBlank()) {
            throw new IllegalStateException("Missing DUKASCOPY_DEMO_PASSWORD");
        }

        final IClient client = ClientFactory.getDefaultInstance();
        final CountDownLatch connectLatch = new CountDownLatch(1);
        final CountDownLatch disconnectLatch = new CountDownLatch(1);

        client.setSystemListener(new ISystemListener() {
            private int lightReconnects = 3;

            @Override
            public void onStart(long processId) {}

            @Override
            public void onStop(long processId) {}

            @Override
            public void onConnect() {
                System.out.println("dukascopy_connect: OK");
                lightReconnects = 3;
                connectLatch.countDown();
            }

            @Override
            public void onDisconnect() {
                System.out.println("dukascopy_disconnect: detected");
                new Thread(new Runnable() {
                    @Override
                    public void run() {
                        if (lightReconnects > 0) {
                            client.reconnect();
                            lightReconnects--;
                        }
                        disconnectLatch.countDown();
                    }
                }).start();
            }
        });

        System.out.println("Connecting to Dukascopy demo...");
        client.connect(jnlpUrl, user, password);

        if (!connectLatch.await(45, TimeUnit.SECONDS)) {
            throw new RuntimeException("Timed out waiting for Dukascopy demo connection");
        }

        System.out.println("dukascopy_connect_check: SUCCESS");
        client.disconnect();
        disconnectLatch.await(5, TimeUnit.SECONDS);
    }
}
