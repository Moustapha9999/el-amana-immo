/**
 * Dev proxy : forward l'IP réelle du navigateur vers FastAPI
 * (X-Forwarded-For / X-Real-IP) pour l'audit.
 */
export default {
  '/api': {
    target: 'http://127.0.0.1:8000',
    secure: false,
    changeOrigin: true,
    xfwd: true,
    logLevel: 'warn',
    configure: (proxy) => {
      proxy.on('proxyReq', (proxyReq, req) => {
        const existing = req.headers['x-forwarded-for'];
        let ip =
          (typeof existing === 'string' && existing.split(',')[0].trim()) ||
          req.socket?.remoteAddress ||
          req.connection?.remoteAddress ||
          '';
        if (ip.toLowerCase().startsWith('::ffff:')) {
          ip = ip.slice(7);
        }
        if (ip) {
          proxyReq.setHeader('x-forwarded-for', ip);
          proxyReq.setHeader('x-real-ip', ip);
        }
      });
    },
  },
};
