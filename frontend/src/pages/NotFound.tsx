import { Compass } from "lucide-react";
import { Link } from "react-router";
import { Button, Card, EmptyState } from "../components/ui";

export default function NotFoundPage() {
  return (
    <Card>
      <EmptyState icon={<Compass className="size-5" />} title="Page not found" action={<Link to="/"><Button>Back to overview</Button></Link>}>
        The page you were looking for does not exist.
      </EmptyState>
    </Card>
  );
}
