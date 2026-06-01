package com.srp.client.renderer;

import com.srp.client.model.InhooSModel;
import com.srp.entity.InhooSEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class InhooSRenderer extends GeoEntityRenderer<InhooSEntity> {

    public InhooSRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new InhooSModel());
    }
}
