import { type RouteConfig, index, route } from '@react-router/dev/routes';

export default [
  index('routes/_index.tsx'),
  route('contracts', 'routes/contracts.tsx'),
  route('chat', 'routes/chat.tsx'),
  route('research', 'routes/research.tsx'),
] satisfies RouteConfig;
