(** Addition is commutative. *)
Lemma addnC : commutative addn.
Proof. Admitted.

Definition double (n : nat) : nat := n + n.

Section Lists.
Lemma map_id : forall xs, map id xs = xs.
Proof. Admitted.
End Lists.
