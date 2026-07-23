import { Suspense } from 'react';
import styles from '../page.module.css';
import { AppHeader } from '@/components/AppHeader';
import { UnsubscribeDigest } from '@/components/UnsubscribeDigest';

// U15 digest unsubscribe route (US-TN2, BR-TN4). The digest email's opt-out link lands
// here; UnsubscribeDigest reads ?token= (search params), so it sits under Suspense.
// Deliberately NOT wrapped in RouteGuard — the signed token authenticates by itself,
// so logged-out recipients unsubscribe without login (verify-email precedent).
export default function UnsubscribePage() {
  return (
    <div className={styles.screen}>
      <AppHeader title="DocSuri" />
      <h2 className={styles.heading}>다이제스트 수신 해지</h2>
      <Suspense fallback={null}>
        <UnsubscribeDigest />
      </Suspense>
    </div>
  );
}
