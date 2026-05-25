import {
  Badge,
  Button,
  Card,
  Center,
  Code,
  Container,
  Group,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { IconCheck, IconHeartbeat, IconX } from "@tabler/icons-react";
import { useEffect, useState } from "react";

type HealthState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: { status: string } }
  | { status: "error"; message: string };

type SystemInfo = {
  app_env: string;
  crewai: { available: boolean; version: string };
  providers_configured: { gemini: boolean; anthropic: boolean; openai: boolean };
};

export function SplashPage() {
  const [health, setHealth] = useState<HealthState>({ status: "idle" });
  const [system, setSystem] = useState<SystemInfo | null>(null);

  async function check() {
    setHealth({ status: "loading" });
    try {
      const [healthRes, systemRes] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/system"),
      ]);
      if (!healthRes.ok) throw new Error(`HTTP ${healthRes.status}`);
      setHealth({ status: "ok", data: await healthRes.json() });
      if (systemRes.ok) setSystem(await systemRes.json());
    } catch (e) {
      setHealth({ status: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  useEffect(() => {
    check();
  }, []);

  return (
    <Center mih="100vh">
      <Container size="sm" w="100%">
        <Stack gap="lg">
          <Stack gap={4}>
            <Title order={1}>yuno</Title>
            <Text c="dimmed">
              Visual platform for non-technical operators. Batch 0 — scaffold.
            </Text>
          </Stack>

          <Card withBorder radius="md" padding="lg">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <IconHeartbeat size={18} />
                <Text fw={600}>Backend</Text>
              </Group>
              <HealthBadge state={health} />
            </Group>

            {system && (
              <Stack gap={4} mt="sm">
                <Text size="sm">
                  Env: <Code>{system.app_env}</Code>
                </Text>
                <Text size="sm">
                  CrewAI {system.crewai.available ? "available" : "missing"} (<Code>{system.crewai.version}</Code>)
                </Text>
                <Text size="sm">
                  Providers configured: {providers(system.providers_configured)}
                </Text>
              </Stack>
            )}

            <Button mt="md" variant="light" onClick={check} loading={health.status === "loading"}>
              Re-check
            </Button>
          </Card>

          <Text size="xs" c="dimmed">
            Batch 1 (single-agent chat) lights up agent CRUD + the first end-to-end run.
          </Text>
        </Stack>
      </Container>
    </Center>
  );
}

function HealthBadge({ state }: { state: HealthState }) {
  if (state.status === "ok")
    return (
      <Badge color="green" leftSection={<IconCheck size={12} />}>
        healthy
      </Badge>
    );
  if (state.status === "error")
    return (
      <Badge color="red" leftSection={<IconX size={12} />} title={state.message}>
        unreachable
      </Badge>
    );
  if (state.status === "loading") return <Badge color="gray">checking…</Badge>;
  return <Badge color="gray">idle</Badge>;
}

function providers(p: SystemInfo["providers_configured"]) {
  const on = Object.entries(p)
    .filter(([, v]) => v)
    .map(([k]) => k);
  return on.length ? on.join(", ") : "none";
}
