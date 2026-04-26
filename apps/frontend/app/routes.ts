import { type RouteConfig, index, route } from '@react-router/dev/routes';

export default [
  index('routes/_index.tsx'),
  route('contracts', 'routes/contracts.tsx'),
  route('chat', 'routes/chat.tsx'),
] satisfies RouteConfig;
