type BeforeQuitEvent = {
  preventDefault(): void;
};

type QuitApplication = {
  on(event: "before-quit", listener: (event: BeforeQuitEvent) => void): void;
  quit(): void;
};

type ManagedService = {
  stop(): Promise<unknown>;
};

export function coordinateManagedServiceShutdown(
  application: QuitApplication,
  service: ManagedService,
  onError: (error: unknown) => void,
): void {
  let quitAfterShutdown = false;
  let shutdownStarted = false;

  application.on("before-quit", (event) => {
    if (quitAfterShutdown) return;

    event.preventDefault();
    if (shutdownStarted) return;
    shutdownStarted = true;

    void service
      .stop()
      .catch(onError)
      .finally(() => {
        quitAfterShutdown = true;
        application.quit();
      });
  });
}

