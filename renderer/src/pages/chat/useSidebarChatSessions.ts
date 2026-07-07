import { useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "../../queryKeys";

export function useSidebarChatSessions() {
  const queryClient = useQueryClient();

  function refreshSidebarSessions() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.sidebarChatSessionsRoot });
  }

  return { refreshSidebarSessions };
}
